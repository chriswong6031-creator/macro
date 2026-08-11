"""engine.marketing.publish_time_content — publish-time mover/theme generation.

`mover` ("Mover of the Day") and `theme_list` ("Theme Tape") posts are the one
family the NIGHTLY content plan deliberately generates but never emits: a "+7%
today" claim written at 23:45 ET is stale by the next morning's opening bell.
This module builds the HONEST version — it runs INSIDE the publisher's slot runs
(10:00 / 13:30 / 16:15 ET on the ubuntu publish workflow), reads the freshest
tape available in that checkout, renders copy from the SAME v3 template banks the
nightly desk uses, enqueues text-only items via the outbox, and hands them to the
existing post-time tape gate (engine/marketing/live_verify.py) which re-verifies
the exact number the copy claims before it may post.

Import constraint: every top-level import here is stdlib or an engine.marketing
module that is itself stdlib-only (movers_source, copywriter, outbox, sentinel,
live_verify). pandas / chart_render / logo_cache / media_publish are NEVER
imported at module top level — the card path below imports them INSIDE the one
function that needs them, so the publisher's import of this module still costs
nothing but stdlib.

EVERY ITEM THIS LANE EMITS NOW CARRIES A HOSTED CARD (2026-07-31). It used to be
text-only "by construction", and that construction killed the lane outright:
#4030's bare-cashtag law quarantines any post that NAMES TICKERS and ships no
picture ("YOU WILL NOT SHIP THESE TEXT ONLY, ID RATHER YOU DESTROY THE ENTIRE
ENGINE" — operator, 2026-07-30), and `mover`/`theme_list` are precisely the two
kinds in that law's _TICKER_ROLLUP_KINDS. From that merge onward every item this
lane produced was unpublishable by construction: generated, queued, quarantined,
forever. The lane now renders and hosts its own card BEFORE it enqueues anything
— theme_list through chart_render.render_watchlist_card (the portrait 4:5 panel
the hot-tape group path already proved), mover through render_chart_v2 on the
local daily bars (the hot-tape single-name tape card) — and a card that will not
HOST means no item at all, per the chartless-DEFER law: better no post than a
naked ticker post.

OPTIONAL WIRE PHRASE PASS (default OFF, 2026-08-08). On top of the deterministic
render sits one optional LLM pass that may re-word the SAME facts more tightly in
the wire register (`phrase_or_template`, modelled on the hot-tape wire desk). It
is armed by two keys (`publish.publish_time_movers.llm.enabled` AND
`MARKETING_LLM_ENABLED`), bounded by a caller-owned 20-second deadline on a
daemon thread, and subset-only: it may not add a number, a cashtag, a link or a
session claim the deterministic copy did not already carry. Disabled, erroring,
timing out, or breaking one wire law all return the template string unchanged, so
a live mover is never blocked or delayed by a model.

Public API (a single orchestrator the publisher calls, plus the optional pass):
    generate_slot_items(root, *, cfg, now, state, approved_due, posted_counts,
                        cap, live, account_filter=None) -> dict
    phrase_or_template(template_text, *, facts, kind, now, cfg) -> dict
    wire_violations(phrase, template_text, *, facts, now, max_chars) -> list[str]
    phrase_stats() / reset_phrase_stats()

Fail-soft law: the whole body is wrapped in try/except → a broken generation
NEVER raises into the legacy publisher flow; it logs a warning and returns a
report with the error noted. In dry-run (live=False) it writes NOTHING and
collects candidates into "would_generate" — and "writes NOTHING" now includes
the CARD: a dry run skips card resolution entirely (no Chrome raster, no data/
SVG+PNG, no R2 PUT) and reports the count as `cards_deferred_dry_run`. Those
candidates are previewed as card-pending; they are never enqueued as if carded.

Display-tier ops (no signal authority, no forward-ledger writes): this only
describes what already moved on the tape.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from engine.marketing import (
    copywriter,
    live_verify,
    market_clock,
    market_facts,
    movers_source,
    outbox,
    sentinel,
    theme_proxy,
)

log = logging.getLogger(__name__)

_CASHTAG_RE = re.compile(r"\$[A-Z]{1,5}\b")

# In-code defaults for the publish.publish_time_movers config block. CONSERVATIVE
# by design: `enabled` is False when the block is absent, so old configs and the
# test-suite fixtures that carry no block are unaffected (generation disabled).
_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "max_per_run": 2,           # network-wide new items per slot run
    "min_abs_mover_pct": 3.0,   # floor for a single-name move claim
    "min_abs_theme_pct": 1.0,   # floor for a theme-average claim
    "max_quote_age_min": 45,    # generation freshness gate (mirrors live_gate)
    "min_active_tiles": 25,     # flat-tape belt: skip when the board isn't moving
    # ── DEFECT 1: the cashtag-spam fingerprint (operator, live post 2026-08-03)
    # How many member cashtags a theme_list POST TEXT may name. The card still
    # lists the full membership (see _CARD_MAX_ROWS); this caps the ENUMERATION
    # IN THE TEXT, which is the half X reads as spam.
    #
    # "you know tagging this many cashtags will get flagged as spam right? like
    # u can do 2-3 but not like all of them" — operator, on a live post that
    # named eight ($COHR $LITE $AXON $META $RBLX $MSFT $GOOGL $U) in one line.
    # Eight cashtags in one post is the account-safety risk, not a style nit:
    # it is the cashtag-piggybacking fingerprint X's spam classifier keys on,
    # and this lane auto-approves and posts with no human in the loop.
    #
    # Config-driven with an in-code default so an operator can retune it without
    # a deploy; 3 is the top of the operator's stated band. The names chosen are
    # the BIGGEST MOVERS in the theme's direction — if we only name three, they
    # should be the three that are the story.
    "max_theme_cashtags_in_text": 3,
    # ── The theme's own ticker (operator, live post 2026-08-05) ───────────────
    # When a group trades as one, the sector ETF or the underlying asset is a far
    # bigger cashtag than any member: $GDX trades 3.7x and $GLD 6.5x the biggest
    # name the post that prompted this was going to name.
    #
    #   "for this kind of theme, shouldnt u be prioritizing tagging the underlying
    #   major ETF or even the underlying commodity/asset class ... these are much
    #   larger tickers that are able to get much more reach"
    #
    # Default ON, and the safety is in the GATE rather than in this flag: the
    # operator's own bound ("some themes ETFS arent that popular ... its case by
    # case basis") is what engine.marketing.theme_proxy enforces, and it refuses
    # every theme whose names out-reach the fund or whose members do not move
    # together. OFF is the kill switch if a tag ever reads wrong on a live post —
    # it restores exactly the member-only behaviour, with no other side effect.
    "theme_proxy_enabled": True,
    # A ticker post ships a picture or it does not ship (see the module
    # docstring). Default ON. The OFF setting is NOT a production escape hatch —
    # it exists so an operator can exercise the copy path on a host with no
    # renderer and no R2 credentials.
    "require_card": True,
}

# A tile counts as "active" for the flat-tape belt when its overlaid 1D move is
# at least this large. Heuristic, not a sentinel cap: a normal RTH session has
# hundreds of S&P names past ±0.5%; a closed market (holiday whose feeds still
# tick) or a stale/static splice has almost none — that is the failure the belt
# catches, because _tape_stale can be anchored fresh by a non-equity quote (BTC
# in the display feed) while every equity pct rides yesterday's board.
_ACTIVE_TILE_MIN_ABS = 0.5

_PROVENANCE = "publisher_live_movers"

#: Folded statuses that still OCCUPY an account's next posting slot.
#:
#: THE DAY-CAP BUG THIS CLOSES (2026-07-31). `_live_queued_pt_today` selected on
#: `created_at[:10] == today` with NO status filter at all, and every account it
#: returned became a HARD skip for the rest of the run ("spacing: one post per
#: account per slot run"). But `state["items"]` holds the item as WRITTEN — its
#: `status` field is frozen at "queued" by outbox.make_item — while the FOLDED
#: status lives in `state["status"]`, which this lane never read. So an item that
#: had already posted, or been quarantined, or failed, or been recalled hours
#: earlier still blocked its account for every remaining slot of the day. With
#: two eligible accounts that capped the entire network at 2 items/day, which is
#: exactly what the ledger shows: pt_generated=2 on precisely one sweep per day
#: and 0 on all the others. The comment said "per slot RUN"; the code said "per
#: DAY". The code now matches the comment.
_PT_PENDING_STATUSES: frozenset[str] = frozenset({"queued", "approved"})

#: In-flight: the item is mid-send in THIS run, so it holds its account's slot,
#: but outbox.posted_today_by_account already counts it (posted/posting) and
#: adding it to the posts-today tally again would double-charge the account.
_PT_INFLIGHT_STATUSES: frozenset[str] = frozenset({"posting"})

#: How many template variants a candidate may be re-rolled through before the
#: lane gives up and drops it for ending on a question (v5: every interrogative
#: tail is bait, whoever it is about). Bounded on purpose: the
#: render is cheap but not free, and a bank that is bait all the way down is a
#: copywriter defect to report, not a loop to grind.
_MAX_TAIL_ROLLS = 4

#: First-person markers, in TWO patterns because the two halves need opposite
#: case rules. FIRST PERSON IS BANNED IN POST COPY (Voice Doctrine v5,
#: 2026-08-11): the subject of a generated sentence is the market, never the
#: author. These patterns are the executable form of that ban on the LLM-phrase
#: path (`llm_phrase_violations` → "first_person_banned").
#:
#: WHAT THEY USED TO BE FOR. Under v4 a first-person marker was the thing that
#: EXCUSED a trailing question — `_tail_is_bait` spared "Am I too slow here?" and
#: rejected "What's your read?" — because the house register was a persona
#: reacting to a trade. v5 retires that register outright, so the exemption is
#: gone and `_tail_is_bait` no longer consults these patterns at all; see its
#: docstring.
#:
#: WHY NOT ONE CASE-SENSITIVE ALTERNATION (the defect this splits). It used to be
#: `\bI\b|\b(?:me|my|…)\b` compiled with no flags, so the lower-case arm only ever
#: matched lower-case pronouns — and a first-person pronoun is upper-case exactly
#: when it opens the sentence, which is the commonest place for it. A phrase
#: opening "My read..." or "Our patience..." carries a first-person stance and
#: went unseen, which on the v4 bait path dropped compliant copy and burned a
#: re-roll (or the whole candidate) for nothing, and on the v5 LLM screen would
#: wave the banned register straight through.
#:
#: The bare "I" arm stays CASE-SENSITIVE deliberately: `\bi\b` under IGNORECASE
#: matches the stray single letter "i" in any enumeration or transliteration, and
#: lower-case "i" is not the English pronoun.
_FIRST_PERSON_I_RE = re.compile(r"\bI\b")
_FIRST_PERSON_OTHER_RE = re.compile(
    r"\b(?:me|my|mine|myself|we|us|our|ours)\b", re.IGNORECASE)


def _has_first_person(text: str) -> bool:
    """True when *text* carries a first-person marker (see the two patterns)."""
    s = str(text or "")
    return bool(_FIRST_PERSON_I_RE.search(s) or _FIRST_PERSON_OTHER_RE.search(s))

#: Rows a theme card shows. The watchlist card supports 3-10; 8 is also
#: ``movers_source.theme_lists``' own ``n`` default, so the card shows every
#: member the theme item carries and the "N names higher" count in the copy is
#: the number of rows in the picture, by construction.
#:
#: WHY 8 SURVIVED THE CASHTAG CAP (defect 1, rewritten 2026-08-03). This constant
#: used to be justified by "the copy names at most 8 cashtags, so 8 keeps the
#: picture and the text describing the SAME names — a card listing a name the
#: post never mentions is its own small lie". That reasoning was wrong, and it is
#: what pinned the text at eight cashtags and gave the account a spam
#: fingerprint. THE CARD IS THE ENUMERATION; THE TEXT IS THE HEADLINE. A picture
#: of eight names captioned with three of them is a summary, not a lie — the same
#: way a chart of a year of bars is not lying because the caption quotes one
#: week. The card may keep all 8 rows PRECISELY BECAUSE the text no longer
#: enumerates them (max_theme_cashtags_in_text).
#:
#: What the two halves must still agree on, and what the session/consistency
#: checks below enforce: the THEME, the COUNT ("8 names higher") and the AVERAGE.
#: Naming 3 of 8 is a summary. Naming a MEMBER the card omits is the actual lie,
#: which is why ``_theme_text_cashtags`` slices its pool to this constant: the
#: named members are a SUBSET of the card's rows. They stopped being a PREFIX of
#: them on 2026-08-05, when the ordering moved from |move| to watchedness — see
#: that function for why prefix-ness was never the honesty property.
#:
#: THE ONE THING THE TEXT MAY NAME THAT THE CARD DOES NOT SHOW is the theme's
#: proxy — the sector ETF or the underlying asset ($GDX, $GLD), added 2026-08-05.
#: That is not a member and it is not held to the subset rule, because it is not a
#: claim about an individual name at all: it is the instrument the group IS, and
#: ``engine.marketing.theme_proxy`` will not release one until the fund provably
#: holds a majority of these very rows (or, for a declared commodity link, until
#: the rows provably move as one). The receipt lives on the outbox item.
_CARD_MAX_ROWS = 8


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def _pt_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve publish.publish_time_movers over the in-code defaults (fail-soft)."""
    out = dict(_DEFAULTS)
    try:
        block = ((cfg or {}).get("publish") or {}).get("publish_time_movers") or {}
        for k, dv in _DEFAULTS.items():
            if k in block:
                if isinstance(dv, bool):
                    v = block[k]
                    out[k] = v if isinstance(v, bool) else (
                        str(v).strip().lower() in {"1", "true", "yes"})
                else:
                    out[k] = type(dv)(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: bad publish.publish_time_movers config "
                    "(%s) — using defaults", exc)
    return out


def _sentinel_knob(cfg: dict | None, key: str, default: Any) -> Any:
    """Read a sentinel: knob from cfg, matching sentinel's in-code fallback."""
    try:
        block = (cfg or {}).get("sentinel") or {}
        if key in block and block[key] is not None:
            return type(default)(block[key])
    except Exception:  # noqa: BLE001
        pass
    return default


# ─────────────────────────────────────────────────────────────────────────────
# Per-call lane eligibility — the ONE place both lanes ask "who may post?"
#
# Both lanes used to filter on ``acc.get("disabled")`` alone, which reads a
# LEGACY key. ``desk_network`` has carried an explicit ``enabled`` since the
# accounts model landed, and ``accounts._config_enabled`` gives ``enabled``
# precedence over ``disabled`` — so an account with ``enabled: false`` and no
# ``disabled`` key (mastermind_news, and every employee desk had one been left
# off) sailed through both filters. Adding a Buffer channel id was then enough to
# make it a live posting target under an unrestricted auto-approve and a -1 cap.
# Liveness now resolves through ``accounts.effective_accounts``, the same
# function the nightly plan builder uses, so the two lanes cannot disagree about
# which accounts exist — and the operator override file is honoured here too.
# ─────────────────────────────────────────────────────────────────────────────

#: Accounts the PER-CALL publish-time lanes may draw, when config names none.
#:
#: Default-restrictive, and it ENFORCES a decision the charter already recorded
#: rather than making a new one: the employee desks launch on non-news/tape kinds
#: (charter §7 sequencing), and their tilts zero ``mover`` and ``event`` to say
#: so. But these two lanes are per-CALL generators — they pick an account from
#: desk_network and build an item directly, never consulting tilt — so a zeroed
#: tilt does not reach them. Without an allowlist an employee desk would launch
#: on exactly the two kinds its own spec sets to 0.00.
#:
#: Employees therefore launch on the NIGHTLY content_studio lane only, which is
#: tilt-governed and rotates variants within a batch so two desks diverge.
#: Charter §6 XG-W2 (cadence resolver) and XG-W3 (desk feeds) are the unlock:
#: when per-account cadence profiles and desk feeds exist, this allowlist is the
#: knob that widens.
_PER_CALL_DEFAULT_ACCOUNTS: tuple[str, ...] = ("flagship", "founder")


def _lane_accounts(cfg: dict | None, lane_key: str) -> frozenset[str]:
    """``publish.<lane_key>.accounts`` allowlist for a per-call lane.

    Absent key → :data:`_PER_CALL_DEFAULT_ACCOUNTS`. Present → EXACTLY that list,
    including an explicit empty list, which means "no account" — default-
    restrictive both ways, so widening the lane is always a visible config edit.
    """
    try:
        block = ((cfg or {}).get("publish") or {}).get(lane_key) or {}
        if "accounts" in block:
            raw = block.get("accounts") or []
            if isinstance(raw, (list, tuple)):
                return frozenset(str(a).strip() for a in raw if str(a).strip())
            log.warning("publish_time_content: publish.%s.accounts is not a list "
                        "— falling back to the default allowlist", lane_key)
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: bad publish.%s.accounts (%s) — "
                    "using the default allowlist", lane_key, exc)
    return frozenset(_PER_CALL_DEFAULT_ACCOUNTS)


def _per_call_eligible(
    cfg: dict | None,
    *,
    lane_key: str,
    root: Path | str | None = None,
    account_filter: str | None = None,
) -> list[dict]:
    """Account dicts a per-call publish-time lane may draw, in config order.

    Four gates, all of which must pass: the account is LIVE (config ``enabled``
    resolved through the accounts model, operator overrides included), it is on
    this lane's allowlist, it has a publish channel id (an item that could never
    post is not worth generating), and it matches any explicit account_filter.
    """
    from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

    pub_channels = ((cfg or {}).get("publish") or {}).get("channels") or {}
    allow = _lane_accounts(cfg, lane_key)

    out: list[dict] = []
    for acc in effective_accounts(cfg, root):
        aid = str(acc.get("id", "") or "")
        if not aid:
            continue
        if not acc.get("enabled"):
            continue
        if aid not in allow:
            continue
        if not str(pub_channels.get(aid, "") or "").strip():
            continue  # no channel id → the item could never post
        if account_filter is not None and aid != account_filter:
            continue
        out.append(acc)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Slot / gating helpers
# ─────────────────────────────────────────────────────────────────────────────

def _slot_label(now: datetime) -> str | None:
    """Map now (UTC) to a slot label, or None outside the posting window.

    Window: 13:30 <= now UTC < 22:00 (the AM/PM/EOD posting slots run in RTH).
      [13:30, 16:30) -> "AM"   (10:00 ET slot)
      [16:30, 19:30) -> "PM"   (13:30 ET slot)
      [19:30, 22:00) -> "EOD"  (16:15 ET slot)
    """
    minutes = now.hour * 60 + now.minute
    if minutes < (13 * 60 + 30) or minutes >= (22 * 60):
        return None
    if minutes < (16 * 60 + 30):
        return "AM"
    if minutes < (19 * 60 + 30):
        return "PM"
    return "EOD"


def _slot_index(slot: str) -> int:
    return {"AM": 0, "PM": 1, "EOD": 2}.get(slot, 0)


def _iso_now(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_report(slot: str | None, *, enabled: bool, quote_source: str = "none",
                  drop: list[dict] | None = None) -> dict:
    return {
        "enabled": enabled,
        "generated": [],
        "would_generate": [],
        "dropped": drop or [],
        "quote_source": quote_source,
        "slot": slot or "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tape freshness + live overlay
# ─────────────────────────────────────────────────────────────────────────────

def _heatmap_stamps(movers_data: dict | None) -> list[str]:
    """Datable stamps for the artifacts that ACTUALLY contributed rows.

    Two corrections to the single `movers_data["asof"]` this replaced.

    WHICH ARTIFACT. That field is the sp500 payload's stamp only, and the sp500
    stamp runs one session behind the themes stamp on every commit measured
    (movers_source module docstring). Dating theme rows by it is the mixed-asof
    failure; dating the gate by it means a themes-only universe is judged by a
    payload that contributed nothing. Each family is now aged by its own
    artifact, and only while that family actually has rows.

    WHICH FIELD. ``asof`` is a DATE. ``live_verify._quote_age_min`` parses it to
    midnight UTC, so at 14:00Z it is 840 minutes old and can NEVER pass a
    45-minute gate — not even when it names today's session. The heatmap-only
    branch was therefore unconditionally stale from the moment it was written,
    which is what 2026-07-31 measured: every in-window sweep logged
    pt_generated=0 / pt_dropped=1 "tape stale". ``generated_utc`` is the payload's
    minute-resolution REFRESH instant and is the only stamp on these artifacts
    that can express "fresh"; the date is kept behind it as the fail-closed last
    resort for a payload that carries no refresh stamp.

    KNOWN LIMIT, stated rather than hidden: generated_utc dates the WRITE, not
    the quote. That is the same class of signal the snapshot branch above already
    trusts in ``tape["asof"]``, and it is not the load-bearing correctness gate —
    the per-candidate session check (a row may not claim a session it is not
    from) and the flat-tape belt are.
    """
    d = movers_data or {}
    stamps: list[str] = []
    if d.get("sp500_tiles"):
        stamps += [d.get("sp500_generated_utc"), d.get("sp500_asof") or d.get("asof")]
    if d.get("theme_tiles"):
        stamps += [d.get("themes_generated_utc"), d.get("themes_asof")]
    if not stamps:
        stamps = [d.get("asof")]
    return [str(x) for x in stamps if x]


def _tape_stale(tape: dict, movers_data: dict | None, now: datetime,
                max_age_min: float) -> bool:
    """True when the freshest tape is older than the generation freshness gate.

    Precedence: if the tape carries per-ticker ts/asof (snapshot/display), use
    live_verify._quote_age_min semantics over the freshest ticker. When the tape
    is heatmap-only (no ts, no asof), fall back to the freshest stamp on the
    heatmap artifacts that actually supplied rows (see :func:`_heatmap_stamps`).
    """
    quotes = (tape or {}).get("quotes") or {}
    asof = (tape or {}).get("asof")
    ages: list[float] = []
    for q in quotes.values():
        age = live_verify._quote_age_min(q, asof, now)
        if age is not None:
            ages.append(age)
    if ages:
        return min(ages) > max_age_min
    # Heatmap-only source: no per-ticker ts and no snapshot asof.
    heat_ages = [a for a in (live_verify._quote_age_min({}, st, now)
                             for st in _heatmap_stamps(movers_data))
                 if a is not None]
    if heat_ages:
        return min(heat_ages) > max_age_min
    # Nothing datable → treat as stale (fail closed: never claim a move we cannot
    # anchor to a fresh timestamp).
    return True


def _live_pct(tape_quotes: dict, ticker: str) -> float | None:
    """The live change_pct for a ticker if the tape has a numeric one, else None."""
    q = tape_quotes.get(str(ticker).upper())
    if not q:
        return None
    return live_verify._f(q.get("change_pct"))


def _overlay_movers(movers_data: dict, tape: dict,
                    *, session: str | None = None) -> dict:
    """Return a COPY of the movers data with live tape pcts overlaid.

    For every sp500 tile and every theme member, if the tape has that ticker with
    a numeric change_pct, replace perf["1D"] with the live change_pct. When the
    tape source includes "snapshot" or "display" (a real quote feed), DROP tiles
    and members that lack a live quote — the heatmap's own 1D is stale next to a
    live feed. When the tape is heatmap-only, the tiles ARE the freshest source,
    so keep them all. Never mutates the loaded dicts in place.

    `session` re-dates the rows this call actually OVERWRITES. A row whose 1D now
    comes from the live tape no longer belongs to the heatmap's session — it
    belongs to the tape's, and the tape has already cleared `_tape_stale`'s
    freshness gate at this point, so it is the current session by construction.
    Rows the tape did not cover keep the stamp their own artifact gave them; that
    is the whole point of carrying the session per row rather than per payload.
    """
    tape_quotes = (tape or {}).get("quotes") or {}
    src = str((tape or {}).get("source") or "")
    has_feed = ("snapshot" in src) or ("display" in src)

    # Carry the per-artifact provenance through: _heatmap_stamps reads it off the
    # OVERLAID dict, and dropping the keys here would silently re-stale the gate.
    out: dict[str, Any] = {
        k: (movers_data or {}).get(k)
        for k in ("asof", "sp500_asof", "themes_asof",
                  "sp500_generated_utc", "themes_generated_utc",
                  "sp500_source", "themes_source")
    }

    new_sp500: list[dict] = []
    for tile in (movers_data or {}).get("sp500_tiles") or []:
        if not isinstance(tile, dict):
            continue
        tkr = tile.get("t", "")
        # ONLY a real feed may overwrite a tile (2026-07-31). When the tape is
        # heatmap-derived its quotes ARE these tiles read back through
        # live_verify._quotes_from_heatmap, so an overlay is at best a no-op —
        # and it stopped being a no-op the moment movers_source.prefer_fresher_session
        # started handing this function rows already improved from the newer
        # themes payload: the round trip put the stale index number back and
        # re-staled the row it had just fixed.
        lp = _live_pct(tape_quotes, tkr) if (tkr and has_feed) else None
        if lp is None:
            if has_feed:
                continue  # a live feed exists but not for this name → stale, drop
            new_sp500.append(dict(tile))  # heatmap-only: keep the tile as-is
            continue
        new_tile = dict(tile)
        new_perf = dict(new_tile.get("perf") or {})
        new_perf["1D"] = lp
        new_tile["perf"] = new_perf
        if session:
            new_tile["asof"] = session   # the number is the tape's now, not the heatmap's
        new_sp500.append(new_tile)
    out["sp500_tiles"] = new_sp500

    new_theme: list[dict] = []
    for tile in (movers_data or {}).get("theme_tiles") or []:
        if not isinstance(tile, dict):
            continue
        new_tile = dict(tile)
        new_members: list[dict] = []
        for m in tile.get("members") or []:
            if not isinstance(m, dict):
                continue
            tkr = m.get("t", "")
            # Feed-only, for the same reason as the tiles above: the heatmap
            # tape is built from the S&P payload, which is the STALER of the two
            # artifacts, so letting it overwrite a themes member would replace a
            # current-session number with a prior-session one.
            lp = _live_pct(tape_quotes, tkr) if (tkr and has_feed) else None
            if lp is None:
                if has_feed:
                    continue
                new_members.append(dict(m))
                continue
            nm = dict(m)
            nm_perf = dict(nm.get("perf") or {})
            nm_perf["1D"] = lp
            nm["perf"] = nm_perf
            if session:
                nm["asof"] = session
            new_members.append(nm)
        new_tile["members"] = new_members
        new_theme.append(new_tile)
    out["theme_tiles"] = new_theme

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Candidate generation (mirrors content_studio nightly wiring)
# ─────────────────────────────────────────────────────────────────────────────

def _radar_tier_map(root: Path, cfg: dict | None) -> dict | None:
    """The radar tier map, only when settings.radar_tiers_enabled is true.

    radar_internal is loaded lazily (kept off the module top-level import set so a
    missing optional dep never breaks the publisher). Fail-soft: absent → None.
    """
    try:
        if not (cfg or {}).get("settings", {}).get("radar_tiers_enabled"):
            return None
        from engine.marketing.radar_internal import load_cashtag_tiers as _lct  # noqa: PLC0415
        tiers = _lct(root)
        if tiers:
            return {t: v["tier"] for t, v in (tiers.get("tickers") or {}).items()}
    except Exception:  # noqa: BLE001
        return None
    return None


def _theme_text_cashtags(members: list[dict], cap: int,
                         tiers: dict[str, Any] | None = None) -> list[str]:
    """The member cashtags the POST TEXT may name — MOST-WATCHED first, capped.

    DEFECT 1. The lane used to hand copywriter ``members[:10]``, so a theme post
    enumerated every name the card shows and shipped eight cashtags in one line
    — the spam fingerprint. The text names at most `cap` of them.

    WHICH ones was |move| descending, and that was a systematic reach leak
    (operator, 2026-08-05). Ranking by |move| is ranking by SMALLNESS: a small
    float moves further on the same dollar flow, so the three biggest movers in a
    group are reliably three of its least-watched tickers — and the lane spent its
    entire 3-cashtag budget on them while its OWN CARD listed bigger names it
    never said out loud:

        Smart Home     named $AEIS ($201M ADV) — card also listed a $14,706M name
        Commodities    named $GFI  ($117M ADV) — card also listed $HL at $599M
        Quantum        named $QUBT           — card also listed $IBM at $3,267M

        "the biggest movers are almost always the smallest floats, just due to
        small caps moving more, this is a big problem eh? we need to use the more
        watched ticker at all times, not the biggest mover."

    So the order is ADV20 descending (``theme_proxy.adv20_musd``), ticker as the
    tiebreak so the choice is deterministic across runs. Every candidate is still
    a name the card SHOWS — the pick is a re-ordering inside the card's own rows,
    never a widening past them, so "naming 3 of 8" stays a summary of the picture.

    WHY THIS DOES NOT NAME A NAME THAT ISN'T THE STORY. The obvious objection to
    ranking by size is that it could tag a mega-cap that barely moved, for reach —
    which is the piggybacking the cashtag cap exists to prevent. It cannot, because
    of what is already in the pool: ``theme_lists`` hands over the theme's top
    members BY ABSOLUTE MOVE IN THE THEME'S OWN DIRECTION, so every candidate here
    has already qualified as a mover on the right side. Watchedness re-orders an
    already-material set; it never admits a name to it. Measured on the 2026-08-02
    board, the two picks this rule changed most were $MSFT at +3.02% inside a
    Smart Home theme averaging +1.81%, and $NVDA at +2.93% inside a Biometrics
    theme averaging +1.19% — both ABOVE their theme's average, i.e. both part of
    the story by the post's own headline number. The copy also names cashtags
    bare, without per-name percentages, so the text makes no claim about any named
    name beyond membership in a group that moved.

    THE INVARIANT WEAKENED, DELIBERATELY, AND WHAT REPLACED IT. The named set used
    to be a PREFIX of the card's rows (both came from one |move|-sorted list). It
    is now a SUBSET but not a prefix — we may name row 5 while row 1 goes unnamed.
    The honesty property was never prefix-ness; it was that the text names nothing
    the picture omits, and ``members`` is sliced to :data:`_CARD_MAX_ROWS` here so
    that holds by construction rather than by upstream coincidence (``theme_lists``
    happens to return at most 8 today — this function no longer depends on it).

    ``tiers``: the cashtag_tiers ``tickers`` block. Absent or ADV-less → falls
    back to the old |move| ordering, because an unranked pick is worse than the
    previous rule, not better.
    """
    pool = [m for m in (members or [])[:_CARD_MAX_ROWS] if m.get("ticker")]
    by_move = sorted(
        pool, key=lambda m: (-abs(float(m.get("pct") or 0.0)), str(m.get("ticker"))))
    n = max(0, int(cap))
    if not tiers:
        return [f"${m['ticker']}" for m in by_move[:n]]

    from engine.marketing.theme_proxy import adv20_musd  # noqa: PLC0415

    scored = [(adv20_musd(tiers, str(m["ticker"])), m) for m in pool]
    if not any(a > 0 for a, _ in scored):
        # Nothing in this cohort is priced. Ordering by a column that is zero
        # everywhere would silently degrade to insertion order — take the rule we
        # can still defend instead.
        return [f"${m['ticker']}" for m in by_move[:n]]
    ordered = sorted(scored, key=lambda am: (-am[0], str(am[1]["ticker"])))
    return [f"${m['ticker']}" for _, m in ordered[:n]]


def _build_candidates(overlaid: dict, root: Path, cfg: dict, pt: dict,
                      *, now: datetime) -> list[dict]:
    """Build interleaved [theme1, mover1, theme2, mover2, ...] candidates.

    Replicates the nightly wiring (content_studio.py ~1126-1239): cashtag_tiers
    via movers_source._load_cashtag_tiers; the radar tier_map only under
    settings.radar_tiers_enabled; min_abs from the publish config. Movers are
    ranked by abs(pct) desc over losers+gainers (nightly convention — losers
    listed first so they win ties). Themes and movers interleave THEME-first.
    Each candidate is a movers-desk-shaped item dict (no copy yet).

    `now` is REQUIRED and is passed straight through to the facts builders as the
    clock the temporal word resolves against, alongside each row's OWN ``asof``
    (defect 2). Both used to be omitted, so ``movers_source.session_phrase`` fell
    back to the real wall clock and to ``last_completed_session`` — which is the
    prior session for the whole of an intraday run, and is exactly how a Monday
    post about Monday's live tape came to say "on Friday".
    """
    tier_map = _radar_tier_map(root, cfg)
    cashtag_tiers: dict | None = None
    try:
        ct = movers_source._load_cashtag_tiers(root)
        if ct:
            cashtag_tiers = ct
    except Exception:  # noqa: BLE001
        cashtag_tiers = None

    mv_result = movers_source.top_movers(
        overlaid, min_abs=float(pt["min_abs_mover_pct"]), tier_map=tier_map)
    tl_result = movers_source.theme_lists(
        overlaid, min_abs_theme=float(pt["min_abs_theme_pct"]),
        cashtag_tiers=cashtag_tiers)

    # Rank movers by |pct| desc; losers first so they win ties (nightly convention).
    all_movers = list(mv_result.get("losers") or []) + list(mv_result.get("gainers") or [])
    all_movers.sort(key=lambda x: abs(x.get("pct", 0)), reverse=True)

    mover_items: list[dict] = []
    used_mover_tickers: set[str] = set()
    for mv in all_movers:
        tkr = mv.get("ticker", "")
        if not tkr or tkr in used_mover_tickers:
            continue
        used_mover_tickers.add(tkr)
        # Trend context for the copy stance (FSLR postmortem 2026-08-03): the
        # same local daily bars the mover card is rendered from decide whether
        # this move landed as a washout bounce / breakout / first crack /
        # capitulation, so the words can never contradict the attached chart.
        # chart_render is imported HERE, not at module top (header law: the
        # publisher's import of this module costs nothing but stdlib), and any
        # failure degrades to the generic bank exactly as before.
        try:
            from engine.marketing import chart_render as _cr  # noqa: PLC0415
            _closes = _cr.load_closes(tkr, root, n=70)
            if _closes:
                mv = dict(mv)
                mv["trend_context"] = movers_source.trend_context(
                    _closes[1], mv.get("pct"))
        except Exception:  # noqa: BLE001 — context is optional, copy is not
            pass
        mover_items.append({
            "type": "mover",
            "ticker": tkr,
            "cashtag": f"${tkr}",
            "_mover_data": mv,
            # asof = the row's own session, never the clock's guess (defect 2).
            "_mover_facts": movers_source.mover_facts(
                mv, now=now, asof=mv.get("asof")),
        })

    text_cap = int(pt["max_theme_cashtags_in_text"])
    # The full tiers rows (not movers_source's flattened {ticker: tier}) — both the
    # watchedness ordering and the proxy's reach leg are denominated in
    # proxies.adv20_musd, which the flattened map throws away.
    # `.get` with the in-code default, not `pt[...]`: `_pt_cfg` always supplies the
    # key, but this function is also called directly with hand-built `pt` dicts, and
    # a KeyError there would take out the whole candidate build over a knob that has
    # a documented default sitting right next to it.
    proxy_on = bool(pt.get("theme_proxy_enabled", _DEFAULTS["theme_proxy_enabled"]))
    proxy_tiers = theme_proxy.load_tiers(root) if proxy_on else {}
    proxy_map = theme_proxy.load_map(root) if proxy_on else {}
    theme_items: list[dict] = []
    for tl in tl_result:
        members = tl.get("members") or []
        if not members:
            continue
        # The names the TEXT may say (defect 1). `_theme_data.members` is left
        # WHOLE — the card enumerates it, and the copy's "N names higher" count
        # and average are computed from it, so truncating it here would make the
        # picture and the breadth fact disagree with each other.
        cashtags = _theme_text_cashtags(members, text_cap, proxy_tiers)
        if not cashtags:
            continue

        # ── The theme's own ticker, when the group trades as one ──────────────
        #
        # A sector ETF or the underlying asset is routinely a far bigger cashtag
        # than any member: on the post that prompted this, $GDX trades 3.7x and
        # $GLD 6.5x the biggest name the text was going to name. The gate in
        # theme_proxy decides whether this theme is one of those — see that module
        # for why all three legs are load-bearing (in short: reach alone would tag
        # $XBI on biotech, whose names do not move together at all).
        #
        # The proxy takes ONE slot and the members keep the rest. The cap is the
        # account-safety limit, not a budget to spend on funds: a theme post that
        # names no names is not a theme post, and stacking $GLD + $GDX would burn
        # two of three slots restating the same idea.
        proxy = None
        if proxy_map:
            proxy = theme_proxy.resolve(
                str(tl.get("theme") or ""),
                [str(m.get("ticker") or "") for m in members[:_CARD_MAX_ROWS]],
                [c.lstrip("$") for c in cashtags],
                pmap=proxy_map, tiers=proxy_tiers, root=root)
        if proxy:
            cashtags = [proxy["cashtag"]] + cashtags[:max(0, text_cap - 1)]

        lead = members[0]
        theme_items.append({
            "type": "theme_list",
            "ticker": "",
            "cashtags": cashtags,
            #: The tagging ARM, stamped so this stops being an unfalsifiable
            #: distribution prior. ADV is a proxy for X reach, not a measurement
            #: of it (theme_proxy.adv20_musd says so where it is read), so the
            #: only way to learn whether proxy-led posts actually travel further
            #: is to label them and let post_metrics compare impressions.
            "_tag_arm": ("proxy_lead" if proxy else "members_only"),
            "_tag_proxy": (dict(proxy) if proxy else None),
            "_theme_data": tl,
            "_theme_facts": movers_source.theme_facts(
                tl, now=now, asof=tl.get("asof")),
            "_lead_ticker": lead.get("ticker", ""),
            "_lead_pct": lead.get("pct"),
            "_theme_name": tl.get("theme", ""),
            "_agg_pct": tl.get("agg_pct"),
            #: How many members the CARD will list. Carried on the candidate so
            #: the text/card agreement check has a number to compare against
            #: without re-deriving the card's own slicing rule.
            "_card_rows": len(members[:_CARD_MAX_ROWS]),
        })

    # Interleave THEME-first: [theme1, mover1, theme2, mover2, ...].
    interleaved: list[dict] = []
    for i in range(max(len(theme_items), len(mover_items))):
        if i < len(theme_items):
            interleaved.append(theme_items[i])
        if i < len(mover_items):
            interleaved.append(mover_items[i])
    return interleaved


# ─────────────────────────────────────────────────────────────────────────────
# Copy (reuse-only — v3 banks via copywriter)
# ─────────────────────────────────────────────────────────────────────────────

def _persona_for(cfg: dict, account: str, voice: str) -> dict:
    """Resolve the persona card the same way content_studio does: by account id,
    then by voice, from cfg copywriter.personas."""
    personas = (cfg or {}).get("copywriter", {}).get("personas", {}) or {}
    return personas.get(account) or personas.get(voice) or {}


def _render_copy(candidate: dict, *, account: str, voice: str, persona: dict,
                 slot: str, has_chart: bool = False,
                 roll: int = 0) -> tuple[str, str, list[str]]:
    """Render (text, headline, violations) for a candidate via the v3 banks.

    Builds a movers-desk item dict exactly like content_studio's nightly ones,
    builds the writer context via copywriter.build_context (facts drive the
    number whitelist), stamps type/voice/slot on the context (LIVE-<slot> so the
    hash key — and thus the chosen template variant — varies across slots for the
    same ticker), and renders with write_posts_deterministic. NEVER calls
    write_posts_llm (no network / model at post time). Post text is the
    emit_from_content_plan convention: headline + "\n\n" + body.
    """
    if candidate["type"] == "mover":
        item = {
            "type": "mover",
            "account": account,
            "ticker": candidate["ticker"],
            "cashtag": candidate["cashtag"],
            "_mover_data": candidate["_mover_data"],
            "_mover_facts": candidate["_mover_facts"],
        }
        facts = candidate["_mover_facts"]
    else:
        item = {
            "type": "theme_list",
            "account": account,
            "ticker": "",
            "cashtags": candidate["cashtags"],
            "_theme_data": candidate["_theme_data"],
            "_theme_facts": candidate["_theme_facts"],
        }
        facts = candidate["_theme_facts"]

    ctx = copywriter.build_context(item, persona=persona or None, facts=facts)
    ctx["type"] = item["type"]
    ctx["voice"] = voice
    # `roll` perturbs the variant-selection hash and NOTHING else: copywriter
    # keys ticker posts on f"{ticker}|{account}|{slot}", so a suffix here rotates
    # deterministically onto a different template without touching the item's own
    # slot label (which stays LIVE-<slot> on the outbox row). See
    # _render_copy_unbaited for why a re-roll is ever needed.
    ctx["slot"] = f"LIVE-{slot}" if not roll else f"LIVE-{slot}-r{roll}"
    # has_chart gates the variants that REFER to an attached picture ("Chart
    # below", "levels are on the chart") — see copywriter._variant_allowed. It was
    # pinned False because this lane shipped text-only; now that every item
    # carries a hosted card, pinning it False would ban the copy that describes
    # the card actually attached to the post.
    ctx["has_chart"] = bool(has_chart)
    if item["type"] == "theme_list":
        # Selection identity only (theme_list skips the ticker-cashtag copy law):
        # a theme item carries ticker "" and a single-context render would always
        # rotate to variant 0. Hashing on the lead member + account + LIVE-slot
        # restores cross-slot/day variety exactly like ticker posts get.
        ctx["ticker"] = candidate.get("_lead_ticker", "")

    posts = copywriter.write_posts_deterministic([ctx])
    post = posts[0] if posts else {"headline": "", "body": "", "violations": ["empty render"]}
    headline = post.get("headline", "") or ""
    body = post.get("body", "") or ""
    text = f"{headline}\n\n{body}" if headline and body else (headline or body)
    return text, headline, list(post.get("violations") or [])


def _tail_is_bait(text: str) -> bool:
    """True when the post ENDS on a question. ANY interrogative tail is bait.

    THE DEFECT (operator voice law, 2026-07-31). All four `publisher_live_movers`
    posts that have ever gone out ended on an unanswered engagement question:
    "Dead-cat bounce or the real dip?", "Which one breaks out first?", "Watching,
    not chasing. What's your read?". A question handed to the timeline commits to
    nothing and can never be wrong.

    THE CARVE-OUT THIS RULE USED TO CARRY, AND WHY IT DIED (Voice Doctrine v5,
    2026-08-11). The v4 rule was about WHO the question was about: a post could
    still end on "?" — and a theme_list HAD to, because copywriter.validate_copy
    required it — as long as the final sentence was the author asking about their
    own position ("Am I too slow here?"). That exemption is now itself a
    violation. v5 bans first person AND question marks in generated post copy, so
    the only shape the carve-out ever spared ("?" plus a first-person marker) is
    doubly forbidden, and keeping the exemption would mean this gate waving
    through the exact register the doctrine exists to delete. validate_copy's
    theme_list "?" REQUIREMENT is inverted to a "?" ban in the same wave, and
    movers_source's `_TAIL_UP`/`_TAIL_DOWN` banks are declarative statements now.

    So the rule is one line: a post ending on "?" is bait, whoever it is about.
    `_has_first_person` survives for the LLM-phrase screen below
    (`llm_phrase_violations`, "no first-person stance"), which is the other half
    of the same doctrine — it just no longer buys a question any forgiveness
    here.

    A post that does not end on a question is not this rule's business at all:
    "Breadth inside the group, not one leader." is already a statement of fact.
    """
    return str(text or "").strip().endswith("?")


#: Every LENGTH violation copywriter can raise ends in "N chars (max M)":
#: validate_copy's "too long: 282 chars (max 275)" and shape_violations'
#: "shape list: 300 chars (max 275)" / "shape two_part: body 290 chars (max 275)".
#: Matched by that trailing shape rather than by a list of prefixes so a new
#: length rule is covered the day it is written — the failure mode this guards
#: against is a length rule the re-roll does NOT recognise, which silently
#: restores the old terminal-on-first-attempt behaviour.
_LENGTH_VIOLATION_RE = re.compile(r"chars\s*\(max\b", re.IGNORECASE)


def _only_length_violations(violations: list[str] | None) -> bool:
    """True when *violations* is non-empty and every entry is a length cap.

    The re-roll gate. A mixed list (too long AND a banned phrase) is NOT
    length-only: the banned phrase is a property of the candidate's facts and no
    variant escapes it, so the caller must see it on attempt 0.
    """
    items = [str(v) for v in (violations or [])]
    return bool(items) and all(_LENGTH_VIOLATION_RE.search(v) for v in items)


#: copywriter.validate_copy's theme_list minimum, matched by its exact emitted
#: shape ("theme_list post must contain ≥4 cashtags; found 3") with the count
#: captured. See _drop_lane_capped_cashtag_violation for why this lane, and only
#: this lane, resolves it against the account-safety cap.
_MIN_CASHTAG_VIOLATION_RE = re.compile(
    r"theme_list post must contain\s*[≥>]=?\s*(\d+)\s*cashtags;\s*found\s*(\d+)",
    re.IGNORECASE)


def _drop_lane_capped_cashtag_violation(
        violations: list[str] | None, cand: dict, cap: int) -> list[str]:
    """Violations with copywriter's theme_list ≥4-cashtag floor removed — and ONLY
    when this lane's own cap is what put the count under it.

    THE COLLISION, NAMED (defect 1). ``copywriter.validate_copy`` requires a
    theme_list post to carry ≥4 member cashtags. That rule was written when the
    text WAS the list: a "theme post" naming two names was not a theme post. The
    card changed the premise — the picture is now the enumeration — and the
    operator's account-safety cap (2-3) sits strictly below copywriter's floor,
    so with the cap applied and the rule enforced this lane would generate a
    theme_list, fail validation on every variant, and emit NOTHING. Silently
    darkening the family is not a fix for the spam fingerprint.

    THIS IS DELIBERATELY NOT A BYPASS AROUND A GENERATION LAW. Four conditions
    must ALL hold, so nothing else can slip through the hole:
      * the candidate is a theme_list that carries a member list at all;
      * the violation matches copywriter's exact emitted shape;
      * the count copywriter FOUND equals the number of cashtags this lane
        deliberately supplied (so a post that lost cashtags to a render bug, or
        that came out under the cap for some other reason, is still terminal);
      * that number is ≤ the configured cap (so raising the cap above
        copywriter's floor retires this exception automatically rather than
        leaving a permanent hole behind).
    Every OTHER violation in the list is returned untouched.

    The right end-state is copywriter's floor becoming card-aware; that lives in
    another lane's file and is reported rather than reached into from here.
    """
    items = [str(v) for v in (violations or [])]
    if not items or str(cand.get("type") or "") != "theme_list":
        return items
    supplied = len(cand.get("cashtags") or [])
    if supplied == 0 or supplied > max(0, int(cap)):
        return items
    kept: list[str] = []
    for v in items:
        m = _MIN_CASHTAG_VIOLATION_RE.search(v)
        if m and int(m.group(2)) == supplied:
            continue
        kept.append(v)
    return kept


def _render_copy_unbaited(candidate: dict, *, account: str, voice: str,
                          persona: dict, slot: str, has_chart: bool,
                          theme_cashtag_cap: int) -> tuple[str, str, list[str], bool]:
    """(text, headline, violations, bait) — copy that does not end on reader-bait.

    The bait can come from a template bank this lane does not own: exactly one
    variant in copywriter's mover pool ends "…Watching, not chasing. What's your
    read?", and the deterministic picker lands on it for some ticker/account/slot
    triples. Dropping the candidate outright would spend a post to punish a
    template, so the lane re-rolls the variant hash instead (see `roll`) and only
    gives up after _MAX_TAIL_ROLLS. The returned `bait` flag is the give-up
    signal; the caller drops and tallies it, which is what surfaces a bank that
    has gone bait all the way down.

    THE SURFACE WIDENED UNDER v5 (2026-08-11) and this is the net that catches
    the difference. `_tail_is_bait` now rejects EVERY interrogative tail, not
    only the ones aimed outward, so a bank variant still carrying a first-person
    question re-rolls here instead of shipping — one lane's un-migrated bank
    costs a re-roll, not a post in the v4 register.

    LENGTH IS RE-ROLLED TOO, for exactly the same reason bait is (defect closed
    2026-07-31). copywriter.validate_copy caps headline+body at 275 characters,
    and the variant banks are not all the same size: on the same candidate the
    'dry, receipts-forward' theme template rendered 282 chars and short-circuited
    the whole loop on attempt 0, while the shorter variants one roll away would
    have shipped. A too-long render is a property of the VARIANT, not of the
    candidate — precisely the condition `roll` exists to escape — so treating it
    as terminal spent a real post to punish a template, which is the failure this
    function was written to stop in the first place.

    Every OTHER violation stays terminal on the first attempt. A number that is
    not in the facts whitelist, a banned phrase, a dangling level reference — all
    of those are properties of the candidate's facts and re-rolling the variant
    hash cannot fix them; grinding the bank would only burn renders and hide the
    real reason from the caller's `copy_violation` report.

    The last attempt's text/violations are returned on failure so the caller's
    existing empty-copy and violation branches still see a real render — a
    candidate that is too long in every variant reports `copy_violation` with the
    real "too long: N chars" string, not a silent drop.

    `theme_cashtag_cap` is this lane's account-safety cap on the number of member
    cashtags a theme_list TEXT may name (defect 1). It is applied here rather
    than at the caller because copywriter's own ≥4-cashtag floor has to be
    resolved BEFORE the length/bait logic runs: it is not a length violation, so
    it would otherwise short-circuit attempt 0 and drop every theme candidate the
    cap touches. See _drop_lane_capped_cashtag_violation for the four conditions
    that keep that resolution from being a general hole.
    """
    text = headline = ""
    violations: list[str] = ["empty render"]
    for attempt in range(_MAX_TAIL_ROLLS):
        text, headline, violations = _render_copy(
            candidate, account=account, voice=voice, persona=persona,
            slot=slot, has_chart=has_chart, roll=attempt)
        violations = _drop_lane_capped_cashtag_violation(
            violations, candidate, theme_cashtag_cap)
        if not text:
            # Not a bait decision: hand this straight back so the caller reports
            # the real reason (empty_copy) rather than "bait".
            return text, headline, violations, False
        if violations:
            if _only_length_violations(violations):
                continue   # a shorter variant may exist — see the docstring
            return text, headline, violations, False
        if not _tail_is_bait(text):
            return text, headline, violations, False
    # Fell out of the loop: either every variant was bait, or every variant was
    # too long. `bait` is the give-up flag for the FORMER only — a length-only
    # exhaustion must surface as copy_violation so the caller's report names the
    # real cause (and so a bank that has grown past the cap is visible as such).
    return text, headline, violations, (not violations)


# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL LLM PHRASE PASS — WIRE REGISTER (the template is the floor)
#
# WHAT THIS IS. Everything above renders DETERMINISTIC v3 template copy, and that
# copy is what ships. This section adds ONE optional pass on top: hand the
# already-rendered template to the shared provider waterfall and ask a model to
# phrase the SAME facts more tightly in the wire register. It is the hot-tape
# wire desk's shape one lane over (`engine/marketing/hot_tape_llm`
# .phrase_or_fallback): the same two-key arming, the same
# `llm_auth.build_providers` waterfall, the same "a rejected phrase is not an
# outcome — the deterministic template posts" law, and the same never-raise
# contract. The template text is passed IN, so this pass never re-renders and
# never reaches back into the copywriter.
#
# A LIVE MOVER IS NEVER BLOCKED OR DELAYED BY A MODEL. Four separate belts:
#   * DEFAULT OFF. `enabled` is False in-code AND the env flag has to agree, so
#     an unconfigured checkout constructs no provider and reads no credential.
#     Every existing config, fixture and test therefore keeps byte-identical copy.
#   * HARD WALL CLOCK. The whole provider path runs on a DAEMON thread behind
#     `_run_with_deadline`; at `budget_s` (20s) the caller stops waiting and the
#     template flows on. Per-provider timeouts are belt, not law: a waterfall
#     that walks four rungs can out-sit any single timeout, and only a deadline
#     the CALLER owns actually bounds the sweep. Daemon, so a hung rung cannot
#     hold the publisher's process open at exit either.
#   * SUBSET-ONLY PHRASING. The model may re-word; it may not add. Numbers,
#     cashtags, links and session claims in the phrase must already be in the
#     template or the facts, so a phrase that clears these checks cannot fail a
#     downstream gate (cashtag breadth, session conflict, the post-time tape
#     gate) that the template itself passed.
#   * NEVER RAISES. Every failure — no credential, provider exception, empty
#     reply, one broken wire law — returns the caller's template UNCHANGED.
#
# EPISTEMICS (CLAUDE.md §Epistemics; same law as the hot-tape desk). The engine
# computes, the model phrases, the LLM never originates a number. This is
# display-tier ops: no ranking, no gating, no forward-ledger write.
# ─────────────────────────────────────────────────────────────────────────────

#: Two-key arming, the same pair the hot-tape wire desk and the nightly
#: copywriter lane use: the config block says the desk is on AND the environment
#: says this process may spend a credential.
_LLM_ENV_FLAG = "MARKETING_LLM_ENABLED"
_LLM_TRUTHY = ("1", "true", "yes")

#: In-code defaults for `publish.publish_time_movers.llm`. Conservative in the
#: same way `_DEFAULTS` is: absent block ⇒ disabled ⇒ the deterministic template,
#: unchanged.
_LLM_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    # THE budget. Everything else is a per-rung guess; this is the number the
    # publisher's slot run actually feels.
    "budget_s": 20.0,
    # Passed EXPLICITLY to build_providers. Codex is a SUBPROCESS, not an HTTP
    # client, and llm_auth falls back to `client_timeout_s` for it when this key
    # is absent — so an HTTP timeout tuned for a socket would silently become the
    # codex process budget. Naming both keeps the two budgets independent.
    "codex_timeout_s": 10.0,
    "client_timeout_s": 4.0,
    # SDK retries defeat the failover walk (the retry re-hits the SAME dead
    # credential before the waterfall sees it). The CHAIN is the retry.
    "client_max_retries": 0,
    "max_tokens": 220,
    #: copywriter.validate_copy caps headline+body at 275, and this phrase
    #: REPLACES both, so 275 is the binding cap. The prompt asks for 260 so the
    #: model leaves the headroom rather than landing on the wall.
    "max_chars": 275,
    #: Runaway guard, not a budget: a slot run emits at most `max_per_run` items.
    "max_calls_per_run": 8,
    # CHATGPT-FIRST, then the Claude pool, then metered rungs (the order the
    # operator set on copywriter.llm 2026-07-29).
    "provider_order": ["codex", "oauth", "anthropic", "deepseek"],
    # TERRA, deliberately. House model-tier law: sol writes long-form copy, terra
    # critiques and WIRES, luna never touches user-facing words. This is a wire
    # lane, so terra is the correct tier — do not "upgrade" it to sol.
    "codex_source_model": "gpt-5.6-terra",
    # One short wire sentence inside a 20-second budget cannot afford a reasoning
    # pass.
    "codex_reasoning_effort": "low",
    "usage_lane": "publish-time-wire",
    "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
    "deepseek_key_env": "DEEPSEEK_API_KEY",
    "deepseek_model": "deepseek-chat",
}

#: Model id for the oauth / anthropic rungs when config.yml names none.
_LLM_DEFAULT_MODEL = "claude-sonnet-4-6"

#: Codepoint ranges that count as emoji. Deliberately broad, and the same set the
#: sibling screen in `engine/marketing/blind_identity` uses: an emoji we fail to
#: spot is an emoji on the timeline, and over-rejecting a decorative glyph costs
#: nothing at all here because the template is always waiting.
#: ESCAPES, not literal glyphs: variation selectors (U+FE00..U+FE0F) are
#: invisible in source, so a literal class here would read as a typo and be
#: "cleaned up" by the next editor.
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # symbols, pictographs, supplements
    "\u2600-\u27BF"           # misc symbols + dingbats
    "\u2B00-\u2BFF"           # arrows and misc symbols
    "\U0001F000-\U0001F2FF"   # mahjong/domino/cards/enclosed
    "\uFE00-\uFE0F"           # variation selectors (the emoji tell)
    "\U0001F1E6-\U0001F1FF"   # regional indicators (flags)
    "]"
)

#: Dash and quote tells. The ASCII hyphen and the straight quote are the only
#: forms the house voice ships; every curly/long variant here is an LLM tell.
_SMART_GLYPHS: tuple[str, ...] = ("—", "–", "―", "‒", "“", "”", "‘", "’", "„", "‟")

#: Engagement CTAs. PHRASES, never bare words: "follow" is ordinary market
#: English ("follow-through"), and a bare-word list would reject clean copy while
#: still missing the fifth bait line nobody has written yet.
_CTA_RES: tuple[re.Pattern[str], ...] = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"\bfollow (?:for|us|me|along for)\b",
    r"\bhit (?:that )?follow\b",
    r"\blike (?:and|&) (?:retweet|share|repost)\b",
    r"\b(?:retweet|repost|rt) if\b",
    r"\b(?:smash|drop) (?:that |a )?(?:like|follow)\b",
    r"\blink in bio\b",
    r"\b(?:comment|sound off|let me know) below\b",
    r"\btag a (?:friend|trader)\b",
    r"\bshare this (?:post|one|with)\b",
    r"\bsubscribe\b",
))

_LLM_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

#: Per-process counters. `phrase_stats()` is what tells an operator whether an
#: ARMED desk is actually serving or quietly falling back on every item.
_LLM_STAT_KEYS = ("calls", "llm", "fallback_validation", "fallback_provider",
                  "fallback_timeout", "off")
_LLM_STATS: dict[str, int] = {k: 0 for k in _LLM_STAT_KEYS}
_LLM_CALLS_THIS_RUN = 0


def phrase_stats() -> dict:
    """Counters for this process: how often the model served vs fell back.

    Keys: ``calls`` (phrase attempts), ``llm``, ``fallback_validation``,
    ``fallback_provider``, ``fallback_timeout``, ``off``, plus a derived
    ``fallback_rate``. A copy, so mutating it is a no-op.
    """
    out = dict(_LLM_STATS)
    calls = out.get("calls", 0)
    out["fallback_rate"] = (round((calls - out.get("llm", 0)) / calls, 4)
                            if calls else 0.0)
    return out


def reset_phrase_stats() -> None:
    """Zero the counters AND the per-run call cap. For tests and dry runs."""
    global _LLM_CALLS_THIS_RUN
    for k in _LLM_STAT_KEYS:
        _LLM_STATS[k] = 0
    _LLM_CALLS_THIS_RUN = 0


def _llm_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve `publish.publish_time_movers.llm` over `_LLM_DEFAULTS` (fail-soft).

    Tolerates the full marketing config (has ``publish``), the ``publish`` block
    (has ``publish_time_movers``), the lane block (has ``llm``), or the ``llm``
    block itself — the same tolerance ``hot_tape_llm._llm_cfg`` gives its caller.
    An unreadable value never fails the pass: it falls back to the default, and a
    default-valued pass is a disabled pass.
    """
    out = dict(_LLM_DEFAULTS)
    block: Any = {}
    try:
        src = cfg or {}
        if isinstance(src.get("publish"), dict):
            src = src.get("publish") or {}
        if isinstance(src.get("publish_time_movers"), dict):
            src = src.get("publish_time_movers") or {}
        block = src.get("llm") if isinstance(src.get("llm"), dict) else src
        if not isinstance(block, dict):
            block = {}
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: bad publish_time_movers.llm config "
                    "(%s) — phrase pass stays off", exc)
        return out

    for k, dv in _LLM_DEFAULTS.items():
        if k not in block or block[k] is None:
            continue
        v = block[k]
        try:
            if isinstance(dv, bool):
                out[k] = v if isinstance(v, bool) else (
                    str(v).strip().lower() in _LLM_TRUTHY)
            elif isinstance(dv, list):
                out[k] = [str(x) for x in v] if isinstance(v, (list, tuple)) else dv
            else:
                out[k] = type(dv)(v)
        except (TypeError, ValueError):
            log.warning("publish_time_content: publish_time_movers.llm.%s is not a "
                        "%s (%r) — using %r", k, type(dv).__name__, v, dv)
    return out


def _resolve_wire_model(llm_cfg: dict) -> str:
    """Model id for the oauth / anthropic rungs.

    `llm.model`, else config.yml's `llm_models.publish_time_wire` /
    `hot_tape_wire` / `marketing_copy`, else the literal default. Reading the
    estate's model registry rather than pinning an id here is what keeps a model
    rename one edit instead of a grep.
    """
    named = str(llm_cfg.get("model") or "").strip()
    if named:
        return named
    try:
        from lib import config as _config  # noqa: PLC0415
        models = (_config.load() or {}).get("llm_models") or {}
        for key in ("publish_time_wire", "hot_tape_wire", "marketing_copy"):
            if models.get(key):
                return str(models[key])
    except Exception:  # noqa: BLE001 — a config read must never cost a post
        pass
    return _LLM_DEFAULT_MODEL


def _cashtags(text: str) -> set[str]:
    """Distinct cashtags in *text*, upper-cased (the module's own `$AAPL` shape)."""
    return {c.upper() for c in _CASHTAG_RE.findall(str(text or "").upper())}


def wire_violations(phrase: str, template_text: str, *,
                    facts: dict | None = None,
                    now: datetime | None = None,
                    max_chars: int = 275) -> list[str]:
    """Wire-register laws the model's phrasing must satisfy. [] = clean.

    The laws, and why each one is here:

    * **length / emptiness** — a wire phrase, not a paragraph. `max_chars`
      mirrors ``copywriter.validate_copy``'s headline+body cap, because this
      phrase replaces both.
    * **no hashtag, no exclamation mark, no emoji** — the register is a wire
      desk, not a promo account, and every one of the three is the fingerprint X
      reads as engagement bait.
    * **no em dash, en dash, horizontal bar or smart quote** — the house dash
      tells (``copywriter.banned_language`` screens the same glyphs on the
      generation side).
    * **no first-person stance** — reuses this module's own ``_has_first_person``
      so the LLM path and the bait-tail rule cannot drift apart.
    * **no engagement CTA** — "follow for more" / "like and retweet" / "link in
      bio" and their siblings.
    * **no invented number** — delegated to
      ``hot_tape_llm.numeric_violations`` against a packet built from the
      TEMPLATE plus the engine-computed facts, so every number in the phrase must
      already have been computed by the engine. This is the whole epistemics law
      in one call, and reusing the hot-tape implementation is what keeps the two
      wire desks agreeing about what "the packet licenses that number" means.
    * **no invented cashtag or link, and no orphaning** — the phrase's cashtags
      must be a subset of the template's, it must keep at least one when the
      template had any (a ticker post that names no ticker is orphaned from its
      ticker), and it may not introduce a URL. Subset-ness is also what makes the
      downstream cashtag-breadth gate unreachable by this path.
    * **no new session claim** — resolved through ``market_clock.session_claims``,
      the estate's one calendar authority, and required to be a subset of the
      template's claims. Without it a model could write "on Friday" over Monday
      rows, which is defect 2 of the 2026-08-03 postmortem re-entering through a
      new door.

    Fail-closed by construction: anything this function cannot evaluate raises
    into its caller's ``except``, which returns the template.
    """
    text = str(phrase or "").strip()
    out: list[str] = []
    if not text:
        return ["empty_phrase"]
    if len(text) > int(max_chars):
        out.append(f"too long: {len(text)} chars (max {int(max_chars)})")
    if "#" in text:
        out.append("hashtag_banned")
    if "!" in text:
        out.append("exclamation_banned")
    if _EMOJI_RE.search(text):
        out.append("emoji_banned")
    for glyph in _SMART_GLYPHS:
        if glyph in text:
            out.append("dash_or_smart_quote_banned")
            break
    if _has_first_person(text):
        out.append("first_person_banned")
    for pat in _CTA_RES:
        hit = pat.search(text)
        if hit:
            out.append(f"engagement_cta: {hit.group(0).lower()}")
            break

    from engine.marketing import hot_tape_llm  # noqa: PLC0415
    # The template is IN the packet, so every number the deterministic copy
    # already says is admissible; `facts` adds the engine's computed numbers the
    # template chose not to print.
    packet = {"template": str(template_text or ""), "facts": facts or {}}
    out.extend(hot_tape_llm.numeric_violations(text, packet))

    tmpl_tags = _cashtags(template_text)
    new_tags = _cashtags(text) - tmpl_tags
    if new_tags:
        out.append(f"cashtag_not_in_template: {sorted(new_tags)[:3]}")
    if tmpl_tags and not _cashtags(text):
        out.append("cashtag_dropped: phrase names no ticker")
    if set(_LLM_URL_RE.findall(text)) - set(_LLM_URL_RE.findall(str(template_text or ""))):
        out.append("link_not_in_template")

    if now is not None:
        p_claims, p_unresolved = market_clock.session_claims(text, now=now)
        if p_unresolved:
            out.append(f"unresolvable_session_claim: {p_unresolved[0]}")
        t_claims, _t_unresolved = market_clock.session_claims(
            str(template_text or ""), now=now)
        extra = p_claims - t_claims
        if extra:
            named = ", ".join(d.isoformat() for d in sorted(extra))
            out.append(f"session_claim_not_in_template: {named}")
    return out


def _wire_system_prompt(max_chars: int) -> str:
    """The phrasing law, stated to the model.

    Deliberately dash-free and quote-plain: a model that has just read an em dash
    writes one, and the dash law would then reject the very phrase the prompt
    asked for (the ``hot_tape_llm._dashless`` lesson, applied to the prompt
    rather than to the repair turn).
    """
    return (
        "You are the wire desk of a market-data publisher. You are given ONE post "
        "our engine already wrote from numbers it already computed. Rewrite it "
        "tighter in the same wire register.\n\n"
        "The engine computes. You phrase. You never originate a fact.\n\n"
        "LAWS\n"
        "1. Use ONLY numbers from the ALLOWED NUMBERS list, written exactly as "
        "shown. Never compute, extend, re-round or add one.\n"
        "2. Use ONLY the cashtags already in the post, and keep at least one.\n"
        "3. Keep the same session. Do not add a day, a date or a weekday the "
        "post does not already name.\n"
        "4. Declarative and unhedged. State the tape flat.\n"
        "5. No advice and no calls. Nothing that tells the reader to do anything.\n"
        "6. No first person. No I, me, my, we, us or our.\n"
        "7. No hashtags. No exclamation marks. No emoji. No engagement asks such "
        "as follow for more, like and retweet, or link in bio.\n"
        "8. The ASCII hyphen is the only dash allowed. Straight quotes only.\n"
        f"9. {max(80, int(max_chars) - 15)} characters maximum. Shorter is better.\n"
        "10. Output the post text only. No JSON, no quotes around it, no "
        "preamble, no sign-off.\n"
    )


def _wire_user_message(template_text: str, facts: dict | None, kind: str) -> str:
    """The user turn: the post to tighten, plus the numbers it is allowed to say."""
    from engine.marketing import hot_tape_llm  # noqa: PLC0415
    packet = {"template": str(template_text or ""), "facts": facts or {}}
    allowed = hot_tape_llm.numbers_whitelist(packet)
    return (
        f"KIND: {kind}\n\n"
        f"POST TO TIGHTEN:\n{template_text}\n\n"
        "ALLOWED NUMBERS (every number in your rewrite must be one of these, "
        "written exactly as shown):\n"
        + "\n".join(f"  {n}" for n in allowed)
    )


def _tidy_phrase(text: str) -> str:
    """Strip the wrappers a model adds despite law 10 — fences and quote pairs."""
    out = str(text or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-zA-Z]*\s*", "", out)
        out = re.sub(r"\s*```$", "", out).strip()
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'":
        out = out[1:-1].strip()
    return out


def _run_with_deadline(fn, budget_s: float) -> tuple[Any, bool]:
    """``(value, timed_out)`` — run *fn* on a DAEMON thread, give up at the budget.

    The publisher's slot run owns the clock, not the provider waterfall. A walk
    over four rungs can out-sit any per-rung timeout (and the codex rung is a
    subprocess, not a socket), so the only bound that actually holds is one the
    CALLER enforces. DAEMON because a thread still waiting on a dead rung must
    not hold the sweep's process open at exit; the abandoned thread's result is
    simply never read.

    An exception on the worker thread is invisible to a `try` around the START of
    that thread, so it is captured and re-raised HERE — otherwise the public
    entry point's ``except`` would never see a dead waterfall and a failed call
    would read as a successful empty one. BaseException is caught (so ``done`` is
    always set and the caller can never hang on a worker that died) but only an
    ``Exception`` is re-raised: a SystemExit/KeyboardInterrupt that somehow
    reached this thread is logged and degraded to a fallback rather than smuggled
    past the entry point's never-raise contract.
    """
    box: dict[str, Any] = {}
    done = threading.Event()

    def _worker() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — surfaced below, never lost
            box["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_worker, name="pt-wire-phrase", daemon=True).start()
    if not done.wait(max(0.1, float(budget_s))):
        return None, True
    err = box.get("error")
    if isinstance(err, Exception):
        raise err
    if err is not None:
        log.warning("publish_time_content: wire phrase worker died on %s",
                    type(err).__name__)
        return None, False
    return box.get("value"), False


def phrase_or_template(template_text: str, *,
                       facts: dict | None = None,
                       kind: str = "mover",
                       now: datetime | None = None,
                       cfg: dict | None = None) -> dict:
    """Phrase one publish-time item in wire voice, or hand back the template.

    NEVER RAISES, and never returns text the caller did not already have unless
    that text cleared every law in :func:`wire_violations`.

    Parameters
    ----------
    template_text:
        The DETERMINISTIC v3 render of this item (headline + blank line + body).
        This is the floor: it is what ships whenever the model path does not
        clear every gate, which is why nothing below can cost a post.
    facts:
        The candidate's engine-computed facts (``movers_source.mover_facts`` /
        ``theme_facts``). Read-only, and only ever used to widen the set of
        numbers the phrase is ALLOWED to say.
    kind:
        ``"mover"`` or ``"theme_list"``. Prompt context only.
    now:
        The run clock. When given, the phrase may not introduce a session claim
        the template did not already make.
    cfg:
        Full marketing config, the ``publish`` block, the lane block, or the
        ``llm`` block itself. Absent ⇒ the in-code defaults ⇒ disabled.

    Returns
    -------
    dict with keys:
        ``text``        always postable: the model's phrasing, or *template_text*.
        ``mode``        ``"llm"`` | ``"fallback_validation"`` |
                        ``"fallback_provider"`` | ``"fallback_timeout"`` | ``"off"``.
        ``provider``    the provider that served, else None.
        ``violations``  the wire laws that forced a fallback (else []).
        ``latency_ms``  wall time of the whole attempt.
    """
    global _LLM_CALLS_THIS_RUN
    started = time.monotonic()
    template = str(template_text or "")
    _LLM_STATS["calls"] += 1

    def _done(mode: str, text: str, *, provider: str | None = None,
              violations: list[str] | None = None) -> dict:
        _LLM_STATS[mode] = _LLM_STATS.get(mode, 0) + 1
        return {
            "text": text,
            "mode": mode,
            "provider": provider,
            "violations": list(violations or []),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    try:
        llm = _llm_cfg(cfg)
        env_on = os.environ.get(_LLM_ENV_FLAG, "").strip().lower() in _LLM_TRUTHY
        if not template or not bool(llm.get("enabled", False)) or not env_on:
            # Disarmed: no provider is constructed, no credential is read, no
            # call is made, and the template comes back byte-identical.
            return _done("off", template)

        if _LLM_CALLS_THIS_RUN >= int(llm["max_calls_per_run"]):
            log.warning("publish_time_content: wire phrase call cap reached (%d) — "
                        "deterministic template ships", int(llm["max_calls_per_run"]))
            return _done("fallback_provider", template)

        max_chars = int(llm["max_chars"])
        system_prompt = _wire_system_prompt(max_chars)
        user_msg = _wire_user_message(template, facts, str(kind or "mover"))
        max_tokens = int(llm["max_tokens"])

        def _attempt() -> tuple[str | None, str | None] | None:
            """Build the waterfall and make ONE call. Returns (text, provider)."""
            from engine import llm_auth  # noqa: PLC0415
            provider_cfg = {
                "provider_order": list(llm["provider_order"]),
                "codex_source_model": str(llm["codex_source_model"]),
                "codex_reasoning_effort": str(llm["codex_reasoning_effort"]),
                "oauth_token_env": str(llm["oauth_token_env"]),
                "deepseek_key_env": str(llm["deepseek_key_env"]),
                "oauth_pool_lane": str(llm["usage_lane"]),
                "usage_lane": str(llm["usage_lane"]),
                # BOTH, explicitly. See `_LLM_DEFAULTS.codex_timeout_s`.
                "codex_timeout_s": float(llm["codex_timeout_s"]),
                "client_timeout_s": float(llm["client_timeout_s"]),
                "client_max_retries": int(llm["client_max_retries"]),
            }
            providers = llm_auth.build_providers(
                provider_cfg,
                opus_model=_resolve_wire_model(llm),
                deepseek_model=str(llm["deepseek_model"]))
            if not providers:
                # ARMED BUT MUTE — the config says the wire desk is on and the
                # env flag agrees, yet no credential is visible, so every item is
                # silently posting the template. The nightly copywriter lane ran
                # in exactly this state for months (2026-07-26 incident).
                # A BARE print at line start: GitHub only parses `::` at column
                # 0, and every logger here prefixes the line, so an annotation
                # routed through log.warning is dropped silently
                # (tests/test_gh_annotation_line_start.py). flush because stdout
                # is block-buffered when piped in Actions.
                print("::warning title=publish-time-wire-mute::Publish-time wire "
                      "phrase pass is ARMED (publish_time_movers.llm.enabled + "
                      "MARKETING_LLM_ENABLED) but no provider credential is "
                      "visible, so every mover and theme post is falling back to "
                      "the deterministic template. Pass CLAUDE_CODE_OAUTH_TOKEN* "
                      "/ ANTHROPIC_API_KEY / DEEPSEEK_API_KEY to this step.",
                      flush=True)
                log.warning("publish_time_content: wire phrase pass armed but no "
                            "provider credential — deterministic templates only")
                return None

            def _do_call(client, model):
                resp = client.messages.create(
                    model=model, max_tokens=max_tokens, system=system_prompt,
                    messages=[{"role": "user", "content": user_msg}])
                if getattr(resp, "stop_reason", None) == "refusal":
                    return None, "stop_refusal", resp
                out = "".join(b.text for b in resp.content
                              if getattr(b, "type", "") == "text")
                return (out.strip() or None), None, resp

            raw, reason, provider = llm_auth.make_call(
                providers, _do_call, context="publish_time_wire")
            if not raw:
                log.info("publish_time_content: no wire phrasing (%s) — "
                         "deterministic template ships", reason or "empty")
                return None
            return str(raw), (str(provider) if provider else None)

        _LLM_CALLS_THIS_RUN += 1
        result, timed_out = _run_with_deadline(_attempt, float(llm["budget_s"]))
    except Exception as exc:  # noqa: BLE001 — a live mover must still post
        log.warning("publish_time_content: wire phrase pass failed (%s: %s) — "
                    "deterministic template ships", type(exc).__name__, exc)
        return _done("fallback_provider", template)

    if timed_out:
        log.warning("publish_time_content: wire phrase pass exceeded its budget — "
                    "deterministic template ships")
        return _done("fallback_timeout", template)
    if not result:
        return _done("fallback_provider", template)

    try:
        raw, provider = result
        phrase = _tidy_phrase(raw)
        violations = wire_violations(
            phrase, template, facts=facts, now=now, max_chars=max_chars)
    except Exception as exc:  # noqa: BLE001 — an unevaluable phrase is a rejected one
        log.warning("publish_time_content: wire phrase check failed (%s: %s) — "
                    "deterministic template ships", type(exc).__name__, exc)
        return _done("fallback_validation", template, violations=["check_error"])

    if violations:
        # No repair turn here, unlike the hot-tape desk. That desk repairs
        # because its fallback is a bare template with no other option; this lane
        # already holds fully-validated v3 copy in hand, so a second call would
        # spend another slice of a 20-second live budget to maybe match what is
        # already sitting there.
        log.warning("publish_time_content: wire phrase rejected (%s) — "
                    "deterministic template ships", "; ".join(violations[:4]))
        return _done("fallback_validation", template, violations=violations)
    return _done("llm", phrase, provider=provider)


def _cand_session(cand: dict) -> str | None:
    """ISO date of the session the candidate's ROWS describe, or None.

    Movers carry the stamp of the sp500 tile they came from (possibly re-dated by
    movers_source.prefer_fresher_session or by the live overlay); themes carry the
    single session all their members agree on, and None when they disagree. None
    is refused upstream — an undatable claim is not publishable.
    """
    if cand.get("type") == "mover":
        src = cand.get("_mover_data") or {}
    else:
        src = cand.get("_theme_data") or {}
    return str(src.get("asof") or "") or None


# ─────────────────────────────────────────────────────────────────────────────
# ONE SESSION PER POST — the mixed-session-claim check (defect 2)
#
# THE DEFECT, in the post that shipped (operator, live 2026-08-03 ~17:30Z):
#
#     "Virtual & Augmented Reality is up across the board today"          ← today
#     "$COHR $LITE $AXON $META $RBLX $MSFT $GOOGL $U"
#     "Virtual & Augmented Reality is +3.7% on average on Friday (8 …)"   ← Friday
#     card header dated 2026-08-03                                        ← today
#
# Three different claims about which session the post is about, in one post,
# published on a Monday. The row-session gate below ("rows dated X, not today")
# was already in place and PASSED — the rows really were Monday's. It asks
# whether the DATA is current; it never looked at what the WORDS said. The body's
# day word came from `movers_source.session_phrase`, which inferred the session
# from the clock (`last_completed_session`) instead of from the row — fixed at
# the source in movers_source — and nothing downstream would have noticed if it
# had not been.
#
# So this is the belt: resolve EVERY temporal claim the rendered text makes back
# to a session date, and refuse the candidate unless they all name the one
# session its rows are from. A rejection, never a warning: this lane
# auto-approves and posts with no human in the loop, so a warning is a post.
#
# The word tables come from market_clock (the estate's single calendar
# authority) rather than being re-listed here — a new "today"-class word added
# there is covered by this check the day it lands, which is the failure mode a
# local copy would silently reopen.
# ─────────────────────────────────────────────────────────────────────────────

#: THE CLAIM RESOLVER LIVES IN market_clock, NOT HERE (generalised 2026-08-06).
#: This lane wrote the weekday / month-day / "today" resolver first, and the
#: publisher's new session-freshness gate needs exactly the same answers for
#: every OTHER lane. A second copy is how two gates start disagreeing about
#: which session "on Friday" names, so the tables and the walk moved next to the
#: calendar they depend on and this name is now an alias. The lookback constants
#: are re-exported because this module's tests pin them by name.
_WEEKDAY_LOOKBACK_DAYS = market_clock._WEEKDAY_LOOKBACK_DAYS
_MONTH_DAY_LOOKBACK_DAYS = market_clock._MONTH_DAY_LOOKBACK_DAYS
_WEEKDAY_CLAIM_RE = market_clock._WEEKDAY_CLAIM_RE
_MONTH_DAY_CLAIM_RE = market_clock._MONTH_DAY_CLAIM_RE

#: (sessions the text claims, unresolvable claims). See
#: :func:`engine.marketing.market_clock.session_claims`.
_session_claims = market_clock.session_claims


def _session_conflict(text: str, *, now: datetime, row_session: str | None,
                      card_session: str | None) -> str | None:
    """The reason this post may NOT ship, or None when its three surfaces agree.

    The three surfaces of a publish-time post are the first line (headline), the
    body, and the card's date stamp. `text` is headline + body — one string,
    because a claim is a claim wherever in the post it sits, and the live defect
    put the two halves of the contradiction in DIFFERENT lines.

    Refuses, in order:
      * a claim that resolves to no session at all (`unresolvable_session_claim`);
      * more than one distinct session claimed (`mixed_session_claim`) — this is
        the "today" + "on Friday" post verbatim;
      * a single claim that is not the session the ROWS are from
        (`wrong_session_claim`);
      * a card dated to a different session than the rows (`card_session_mismatch`).

    Text carrying NO temporal claim is honest and passes: the day word degrades
    to nothing when it cannot be justified (market_clock's fail direction), and
    a post with no session word makes no session claim to be wrong about.
    """
    row = market_clock._as_date(row_session) if row_session else None
    if row is None:
        # Undatable rows are already refused by the row-session gate; saying so
        # here too keeps this function total rather than trusting a caller order.
        return f"rows carry no parseable session ({row_session!r})"

    claims, unresolved = _session_claims(text, now=now)
    if unresolved:
        return f"unresolvable_session_claim: {unresolved[0]}"

    if len(claims) > 1:
        named = ", ".join(d.isoformat() for d in sorted(claims))
        return (f"mixed_session_claim: one post claims {len(claims)} sessions "
                f"({named}); rows are {row.isoformat()}")

    if claims:
        only = next(iter(claims))
        if only != row:
            return (f"wrong_session_claim: copy says {only.isoformat()}, "
                    f"rows are {row.isoformat()}")

    card = market_clock._as_date(card_session) if card_session else None
    if card is not None and card != row:
        return (f"card_session_mismatch: card dated {card.isoformat()}, "
                f"rows are {row.isoformat()}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# The picture — a ticker post ships one or it does not ship
# ─────────────────────────────────────────────────────────────────────────────

def _slug(s: str) -> str:
    """Lower-case, hyphenated, filesystem/URL-safe fragment of a label."""
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-") or "x"


def _theme_card_title(cand: dict) -> str:
    """The card's hero line. Plain words, and it says nothing the post does not."""
    theme = str(cand.get("_theme_name") or "").strip()
    direction = str((cand.get("_theme_data") or {}).get("direction") or "")
    verb = "selling off" if direction == "down" else "bid up"
    return f"{theme} {verb}".strip() if theme else f"A group {verb}"


def _theme_card_subtitle(cand: dict) -> str | None:
    """The panel's caption: the breadth fact, straight out of the theme item.

    Deliberately NOT a second stance. The post text carries the read, and a card
    that argues alongside it can contradict it; every number here is one the
    theme item already authorised, so the picture cannot invent anything.
    """
    tl = cand.get("_theme_data") or {}
    members = tl.get("members") or []
    agg = tl.get("agg_pct")
    if not members or agg is None:
        return None
    way = "lower" if str(tl.get("direction") or "") == "down" else "higher"
    try:
        return f"{len(members)} names {way}, average {float(agg):+.1f}%"
    except (TypeError, ValueError):
        return None


def _resolve_card(cand: dict, *, root: Path, cfg: dict, as_of: str,
                  now: datetime, slot: str) -> dict[str, Any]:
    """Draw + host the card for one candidate. {"media", "published", "reason"}.

    SAME CONTRACT AS scripts/hot_tape_radar.resolve_group_card / resolve_chart,
    on purpose: that lane already proved both renderers against this exact
    publish_card seam (SVG + PNG on disk, PNG to R2, public https URL back), and
    one shared contract is what keeps the two from drifting into two lookalike
    card families the way the 2026-07-26 incident did.

      * theme_list → render_watchlist_card. A price chart was never the answer
        for a group; the watchlist panel is the card written for exactly this
        ("a plain multi-ticker text post … as a screenshot of a premium SaaS
        watchlist panel"). Rows come straight off the theme item, so the picture
        cannot name a ticker or a number the copy did not already authorise.
      * mover → render_chart_v2 on local daily bars, configured byte-identically
        to the hot-tape TAPE card: no marker, no highlight disc, no SETUP pill.
        This post reports the tape, it does not claim an entry.

    Bars come from the DEFAULT curated trees (data/baskets/ohlcv, data/stocks) —
    2,993 committed parquets that a shallow ubuntu checkout already carries. This
    lane deliberately does NOT opt into data/massive_stock_day: that store is
    neither split-adjusted nor kept current, and every name this lane can pick is
    an S&P 500 constituent, so the curated trees cover the universe.

    NEVER raises. Every failure path returns media=None with a named reason, and
    the caller drops the candidate rather than shipping it bare.
    """
    out: dict[str, Any] = {"media": None, "published": {}, "reason": "no-card"}
    kind = str(cand.get("type") or "")
    try:
        from engine.marketing.chart_render import chart_cta_enabled  # noqa: PLC0415
        cta = chart_cta_enabled(cfg)
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"renderer-unavailable: {exc}"
        return out

    stamp = now.strftime("%H%M")
    rows: list[dict] = []
    ticker = ""
    if kind == "theme_list":
        chart_id = f"ptlive-theme-{_slug(cand.get('_theme_name') or '')}-{stamp}Z"
        rows = [
            {"ticker": str(m.get("ticker") or ""), "price": None,
             "pct_change": m.get("pct")}
            for m in ((cand.get("_theme_data") or {}).get("members") or [])[:_CARD_MAX_ROWS]
            if m.get("ticker")
        ]
        if not rows:
            out["reason"] = "no-rows"
            return out
        try:
            from engine.marketing.chart_render import render_watchlist_card  # noqa: PLC0415
            svg = render_watchlist_card(
                _theme_card_title(cand), rows,
                as_of=as_of,
                subtitle=_theme_card_subtitle(cand),
                logo_root=root,
                # Portrait 4:5 — the tallest image X renders un-cropped in a
                # phone timeline, and the geometry the group card already uses.
                width=1080, height=1350, cta=cta,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("publish_time_content: theme card render failed for %s: %s",
                        chart_id, exc)
            out["reason"] = "render-failed"
            return out
    else:
        ticker = str(cand.get("ticker") or "").upper()
        if not ticker:
            out["reason"] = "no-ticker"
            return out
        chart_id = f"ptlive-mover-{ticker.lower()}-{stamp}Z"
        try:
            from engine.marketing.chart_render import (  # noqa: PLC0415
                load_ohlcv_windowed,
                render_chart_v2,
            )
            windowed = load_ohlcv_windowed(ticker, root)
            if not windowed or not windowed[0] or not windowed[0][0]:
                out["reason"] = "no-bars"
                return out
            (dates, o, h, low, c, volume), warmup = windowed
            svg = render_chart_v2(
                ticker=ticker, dates=dates, o=o, h=h, l=low, c=c, volume=volume,
                timeframe="DAILY",
                marker_index=None, highlight_index=None, pct_from_index=None,
                show_indicators=True, indicators=("volume", "macd"),
                warmup=warmup, volume_overlay=True, subpanel_h=190, height=880,
                company_name=str((cand.get("_mover_data") or {}).get("name") or ticker),
                logo_root=root, cta=cta,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("publish_time_content: mover card render failed for %s: %s",
                        chart_id, exc)
            out["reason"] = "render-failed"
            return out

    try:
        from engine.marketing.media_publish import publish_card  # noqa: PLC0415
        published = publish_card(svg, chart_id=chart_id, as_of=as_of, root=root)
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: publish_card failed for %s: %s",
                    chart_id, exc)
        published = {}
    out["published"] = dict(published or {})
    out["published"]["chart_id"] = chart_id

    url = str((published or {}).get("media_url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        # Buffer fetches a URL; a repo path is not something X can load. No hosted
        # PNG means no picture, and no picture means no post.
        out["reason"] = "no-media-url"
        return out

    entry: dict[str, Any] = {
        "kind": "chart_svg",
        "path": (published.get("svg_path")
                 or f"data/marketing/outbox/media/{as_of}/{chart_id}.svg"),
        "chart_id": chart_id,
        "media_url": url,
    }
    if kind == "theme_list":
        entry["tickers"] = [r["ticker"] for r in rows]
    else:
        entry["ticker"] = ticker
    if published.get("media_png_path"):
        entry["media_png_path"] = published["media_png_path"]
    out["media"] = entry
    out["reason"] = "ok"
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Ledger-derived today-state (posts-today + existing-today dedupe corpus)
# ─────────────────────────────────────────────────────────────────────────────

def _existing_today_items(state: dict, today: str) -> list[dict]:
    """Every item that belongs to 'today' — as_of==today OR created_at date==today.

    This is the corpus for per-day dedupe (mover ticker / theme name) and the
    near-dup gate (jaccard vs any existing today text), across all accounts and
    all statuses.
    """
    items = state.get("items") or {}
    out: list[dict] = []
    for it in items.values():
        as_of = str(it.get("as_of") or "")
        created = str(it.get("created_at") or "")
        if as_of == today or created[:10] == today:
            out.append(it)
    return out


def _live_pt_today(state: dict, today: str,
                   statuses: frozenset[str]) -> list[dict]:
    """This lane's items created today whose FOLDED status is in `statuses`.

    THE FOLDED STATUS IS THE ONLY ONE THAT MEANS ANYTHING HERE. `state["items"]`
    is the item as WRITTEN — outbox.make_item pins `status` to "queued" at
    creation and nothing ever rewrites that row — while every later transition
    lands in `state["status"]`, which fold_state computes from the ledger. Reading
    the item's own field (or, as this did, reading no status at all) makes a
    posted / quarantined / failed / recalled item indistinguishable from a live
    one for the rest of the day. See _PT_PENDING_STATUSES for what that cost.
    """
    status_map = (state or {}).get("status") or {}
    out: list[dict] = []
    for iid, it in ((state or {}).get("items") or {}).items():
        if it.get("provenance") != _PROVENANCE:
            continue
        if it.get("kind") not in {"mover", "theme_list"}:
            continue
        if str(it.get("created_at") or "")[:10] != today:
            continue
        if status_map.get(iid, str(it.get("status") or "queued")) not in statuses:
            continue
        out.append(it)
    return out


def _live_pending_pt_today(state: dict, today: str) -> list[dict]:
    """Items this lane already made today that NO other counter sees yet.

    queued/approved only: they have not posted, so posted_today_by_account does
    not count them, and they may still auto-approve this very run — so they are
    charged against the day's cap here. Including posting/posted would
    double-charge, since that function already counts both.
    """
    return _live_pt_today(state, today, _PT_PENDING_STATUSES)


def _live_occupying_pt_today(state: dict, today: str) -> list[dict]:
    """Items still holding their account's next posting slot (queued/approved/
    posting). This is the set that BLOCKS an account for the rest of the run —
    and it is a strict subset of "created today", which is what it used to be."""
    return _live_pt_today(state, today, _PT_PENDING_STATUSES | _PT_INFLIGHT_STATUSES)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def generate_slot_items(
    root: Path | str,
    *,
    cfg: dict,
    now: datetime,
    state: dict,
    approved_due: list[dict],
    posted_counts: dict[str, int] | None = None,
    cap: int,
    live: bool,
    account_filter: str | None = None,
) -> dict:
    """Generate publish-time mover/theme items for the current slot run.

    Returns a report dict {enabled, generated:[ids], would_generate:[...],
    dropped:[{reason, detail}], quote_source, slot, cards_unhosted,
    cards_deferred_dry_run}. NEVER raises — the whole body is fail-soft; on error
    it logs a warning and returns a report with the error noted.

    In dry-run (live=False) it writes NOTHING and fills would_generate; enqueues
    only when live is True. NOTHING is literal: card resolution is skipped too,
    so a dry sweep costs no Chrome raster, no data/ write and no R2 upload
    (`cards_deferred_dry_run` counts the candidates whose card was deferred).

    `posted_counts` is accepted for API completeness (the publisher passes its
    as_of-based tally) but the cap decision uses the LEDGER-based posts-today this
    module computes from `state` — as_of counting undercounts nightly items that
    carry yesterday's as_of.
    """
    slot: str | None = None
    try:
        r = Path(root)
        pt = _pt_cfg(cfg)

        if not pt["enabled"]:
            return _empty_report(None, enabled=False,
                                 drop=[{"reason": "disabled",
                                        "detail": "publish.publish_time_movers.enabled is false"}])

        # ── Gate 1: weekday + posting window ────────────────────────────────
        if now.weekday() >= 5:  # Sat/Sun
            return _empty_report(None, enabled=True,
                                 drop=[{"reason": "not_weekday", "detail": now.strftime("%A")}])
        slot = _slot_label(now)
        if slot is None:
            return _empty_report(None, enabled=True,
                                 drop=[{"reason": "outside_window",
                                        "detail": f"{now.strftime('%H:%M')}Z not in [13:30,22:00)"}])

        dropped: list[dict] = []

        # `today` is the CURRENT US SESSION date. Inside this lane's window
        # (13:30-22:00 UTC == 09:30-18:00 ET) the UTC date and the ET date are the
        # same calendar day, so `now`'s UTC date names the session without a tz
        # lookup. Hoisted above the loads because every row-session comparison
        # below needs it.
        today = now.strftime("%Y-%m-%d")

        # ── Load tape + heatmap ─────────────────────────────────────────────
        tape = live_verify.load_live_quotes(r)
        quote_source = str(tape.get("source") or "none")
        # prefer_fresher_session re-dates every S&P row the themes payload also
        # carries. The sp500 close cache ran one session behind the finviz capture
        # on every commit measured, so without this the whole mover family is
        # refused as stale-session on any heatmap-only sweep while the identical
        # numbers sit in the themes payload, dated correctly.
        _raw_movers = movers_source.load_movers(r)
        movers_data = (movers_source.prefer_fresher_session(_raw_movers)
                       if _raw_movers else None)
        if not movers_data:
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "no_heatmap",
                                        "detail": "movers_source.load_movers returned None"}])

        # ── Gate 2: generation freshness ────────────────────────────────────
        if _tape_stale(tape, movers_data, now, float(pt["max_quote_age_min"])):
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "tape stale",
                                        "detail": f"freshest tape older than "
                                                  f"{pt['max_quote_age_min']}m ({quote_source})"}])

        # ── Live overlay + candidates ───────────────────────────────────────
        # session=today re-dates only the rows the tape actually overwrote — the
        # tape has already cleared the freshness gate above, so a row it supplies
        # belongs to the current session by construction.
        overlaid = _overlay_movers(movers_data, tape, session=today)

        # ── Gate 3: flat-tape belt ──────────────────────────────────────────
        # The market must actually be MOVING before we claim anything did: a
        # holiday (weekday, crypto still ticking → _tape_stale passes) or a
        # static delayed splice leaves ~every name near 0%. Counted over the
        # union of everything generation draws from — S&P tiles AND theme
        # members (deduped by ticker) — so a theme-only universe is measured
        # by its members, not an absent index board. Fail closed.
        _active_seen: dict[str, float] = {}
        for t in overlaid.get("sp500_tiles") or []:
            tkr = str(t.get("t") or "")
            if tkr:
                _active_seen[tkr] = live_verify._f((t.get("perf") or {}).get("1D")) or 0.0
        for tt in overlaid.get("theme_tiles") or []:
            for m in tt.get("members") or []:
                tkr = str(m.get("t") or "")
                if tkr and tkr not in _active_seen:
                    _active_seen[tkr] = live_verify._f((m.get("perf") or {}).get("1D")) or 0.0
        active_tiles = sum(1 for v in _active_seen.values()
                           if abs(v) >= _ACTIVE_TILE_MIN_ABS)
        if active_tiles < int(pt["min_active_tiles"]):
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "tape_flat",
                                        "detail": f"only {active_tiles} tiles moved "
                                                  f"≥{_ACTIVE_TILE_MIN_ABS}% (min "
                                                  f"{pt['min_active_tiles']}; closed market?)"}])

        candidates = _build_candidates(overlaid, r, cfg or {}, pt, now=now)
        if not candidates:
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "no_candidates",
                                        "detail": "no mover/theme cleared the min_abs floors"}])

        # ── Today-state (ledger-based) ──────────────────────────────────────
        # (`today` is hoisted above the artifact loads — see there.)
        posted_today = outbox.posted_today_by_account(state, today)
        for it in _live_pending_pt_today(state, today):
            acct = it.get("account", "")
            posted_today[acct] = posted_today.get(acct, 0) + 1
        # This run's already-selected approved_due items also consume a slot.
        for it in (approved_due or []):
            acct = it.get("account", "")
            posted_today[acct] = posted_today.get(acct, 0) + 1

        existing_today = _existing_today_items(state, today)
        # Accounts that already have an approved_due item this run (spacing law:
        # one post per account per slot run).
        due_accounts = {it.get("account", "") for it in (approved_due or [])}
        # Accounts whose slot is still OCCUPIED by one of this lane's items
        # (queued/approved/posting). An item that already posted, quarantined,
        # failed or was recalled does NOT hold the account — that conflation is
        # what capped the whole network at 2 posts/day (see _PT_PENDING_STATUSES).
        for it in _live_occupying_pt_today(state, today):
            due_accounts.add(it.get("account", ""))

        # ── Eligible accounts (deterministic, config order) ─────────────────
        # LIVE + on this lane's allowlist + has a channel — see _per_call_eligible.
        accounts = (cfg or {}).get("desk_network", {}).get("accounts", []) or []
        eligible = [str(a.get("id", "")) for a in _per_call_eligible(
            cfg, lane_key="publish_time_movers", root=r,
            account_filter=account_filter)]
        if not eligible:
            return _empty_report(slot, enabled=True, quote_source=quote_source,
                                 drop=[{"reason": "no_eligible_accounts",
                                        "detail": "no live, lane-allowed account has a publish channel id (or filter mismatch)"}])

        voice_by_id = {str(a.get("id", "")): a.get("voice", "authoritative desk")
                       for a in accounts}

        # Rotate the starting account so the same desk doesn't always lead.
        start = (now.timetuple().tm_yday + _slot_index(slot)) % len(eligible)
        rotated = eligible[start:] + eligible[:start]

        # Sentinel knobs (read from cfg with sentinel in-code fallbacks — never
        # hardcode a cap constant here).
        near_dup_thresh = float(_sentinel_knob(cfg, "near_dup_jaccard",
                                               sentinel._DEFAULT_NEAR_DUP_JACCARD))

        # Per-account caps come from the SAME tier resolver the plan-time gate
        # uses (sentinel.resolve_ramp): this lane auto-approves its own output, so
        # if it read the base block directly a cold account would auto-post the
        # very shapes the D08 ramp exists to withhold. `today` is derived from the
        # injected `now`, so the resolution is as deterministic as the caller's
        # clock — the tier itself never reads a clock of its own.
        _ramp = sentinel.resolve_ramp(cfg or {}, today, root=r)

        def _acct_caps(aid: str) -> dict[str, Any]:
            entry = _ramp["accounts"].get(aid)
            return entry["caps"] if entry else _ramp["fallback"]

        max_per_run = int(pt["max_per_run"])

        # Pre-compute today token sets for the near-dup gate.
        existing_token_sets = [sentinel._token_set(_item_full_text(it)) for it in existing_today]

        generated: list[str] = []
        would_generate: list[dict] = []
        cards_unhosted = 0          # tallied, then annotated once at the end
        #: Candidates whose card was NOT drawn because this is a dry run. They
        #: are previewed, never enqueued — the number belongs in the report so a
        #: reader of a dry-run summary knows the cards are pending, not hosted.
        cards_deferred_dry_run = 0
        #: Per-mode tally of the optional wire phrase pass (see
        #: `phrase_or_template`). Reported so an ARMED desk that is silently
        #: falling back on every item is visible as a number rather than as an
        #: absence — "armed but mute" is the failure this lane inherits.
        llm_phrase_modes: dict[str, int] = {}
        accepted_texts: list[frozenset[str]] = []
        assigned_accounts: set[str] = set()
        acct_cursor = 0

        for cand in candidates:
            if (len(generated) + len(would_generate)) >= max_per_run:
                break
            if assigned_accounts >= set(rotated):
                # Every postable account already took an item this run — no
                # later candidate can land. One summary row, not one per drop.
                dropped.append({"reason": "accounts_exhausted",
                                "detail": f"all {len(assigned_accounts)} eligible "
                                          f"account(s) assigned this run"})
                break

            lead_ticker = (cand["ticker"] if cand["type"] == "mover"
                           else cand.get("_lead_ticker", ""))
            lead_cashtag = f"${lead_ticker}" if lead_ticker else ""

            # ── Session gate: never claim a session these rows are not from ──
            # Every template in the mover/theme banks says "today" in its own
            # words, and this lane cannot rewrite copywriter's banks. So a row
            # from a prior session has exactly one honest outcome here: skip it.
            # (The freshness gate above asks "is the ARTIFACT fresh"; this asks
            # the different and load-bearing question "is the ROW from the
            # session the copy is about" — the mixed-asof law.)
            cand_session = _cand_session(cand)
            if cand_session != today:
                dropped.append({
                    "reason": "stale_session",
                    "detail": f"{lead_cashtag or cand['type']}: rows dated "
                              f"{cand_session or 'unknown'}, not {today}",
                })
                continue

            # ── Per-day dedupe (any account/status) ─────────────────────────
            if cand["type"] == "mover":
                if any(it.get("kind") == "mover"
                       and str((it.get("source") or {}).get("ticker") or "").upper() == cand["ticker"].upper()
                       for it in existing_today):
                    dropped.append({"reason": "dup_today_mover", "detail": cand["ticker"]})
                    continue
            else:
                theme_name = cand.get("_theme_name", "")
                if any(it.get("kind") == "theme_list"
                       and str((it.get("source") or {}).get("theme") or "") == theme_name
                       for it in existing_today):
                    dropped.append({"reason": "dup_today_theme", "detail": theme_name})
                    continue

            # ── Ramp gate: theme_list does not ship from a cold account ─────
            # A theme_list carries ≥4 member cashtags by format — the cashtag-
            # piggybacking fingerprint (D08 R3) — so the tier row withholds the
            # whole format until week 5. Mirrors the plan-tier ramp_theme_list
            # quarantine; without it this lane would auto-approve around the gate.
            if cand["type"] == "theme_list":
                if not any(_acct_caps(a)["theme_list_allowed"] for a in rotated):
                    dropped.append({
                        "reason": "ramp_theme_list",
                        "detail": f"{cand.get('_theme_name', '') or lead_cashtag}: "
                                  f"no eligible account is past the theme_list ramp gate",
                    })
                    continue

            # ── Pick an eligible account for this candidate ─────────────────
            chosen: str | None = None
            for _ in range(len(rotated)):
                aid = rotated[acct_cursor % len(rotated)]
                acct_cursor += 1
                if aid in assigned_accounts:
                    continue
                if aid in due_accounts:
                    continue  # spacing: one post per account per slot run
                # Ledger-based daily cap, tier-narrowed. TWO bugs lived on this
                # line. (1) The bare `>= cap` treated the UNLIMITED sentinel as a
                # cap of -1, so `0 >= -1` was true for every account and this
                # lane generated NOTHING from 2026-07-24 onward — the negative
                # cap must be routed through the same guarded shape outbox.enqueue
                # uses (`cap >= 0 and …`). (2) It read only the base cap, so once
                # unbounded a week-1 desk had no post-time ceiling at all;
                # stricter_daily_cap folds in the account's ramp tier.
                _aid_cap = outbox.stricter_daily_cap(
                    cap, _acct_caps(aid)["max_posts_per_account_per_day"])
                if _aid_cap >= 0 and posted_today.get(aid, 0) >= _aid_cap:
                    continue
                if cand["type"] == "theme_list" and not _acct_caps(aid)["theme_list_allowed"]:
                    continue  # this desk is still ramping — see the gate above
                # Per-account same-cashtag day cap: skip an account already
                # carrying an item today with this candidate's ticker or lead
                # cashtag in its text (sentinel max_same_cashtag_per_account_per_day,
                # tier-narrowed for a ramping desk).
                if _account_same_cashtag_today(existing_today, aid, lead_ticker,
                                               lead_cashtag) \
                        >= _acct_caps(aid)["max_same_cashtag_per_account_per_day"]:
                    continue
                chosen = aid
                break
            if chosen is None:
                dropped.append({"reason": "no_account",
                                "detail": f"no eligible account for {lead_cashtag or cand['type']}"})
                continue

            voice = voice_by_id.get(chosen, "authoritative desk")
            persona = _persona_for(cfg or {}, chosen, voice)

            # ── The picture, BEFORE the copy ────────────────────────────────
            # Order matters twice over. A card that will not host means no item,
            # so paying for the render before the copy costs nothing on the drop
            # path; and the copy's has_chart flag — which template variants may
            # say "levels are on the chart" — can only be answered honestly once
            # the card actually exists.
            #
            # DRY-RUN SKIPS THE CARD ENTIRELY (defect closed 2026-07-31). This
            # function's contract — stated in its own docstring and the module
            # header — is that live=False "writes NOTHING". `_resolve_card` is not
            # a read: it rasterises the SVG through Chrome and hands it to
            # media_publish.publish_card, which writes the SVG and PNG under
            # data/ and PUTs the PNG to R2. So every scheduled dry sweep was
            # paying a Chrome raster plus an R2 upload per candidate and leaving
            # data/ dirty, against the house law that intraday lanes discard
            # data/ writes. The comment that used to sit here ("Rendered in
            # dry-run too: a dry run that skipped the card would report items
            # that could never ship") argued for the side effect — but a dry run
            # is a plan preview, and the honest preview of an unrendered card is
            # "card pending", not a hosted URL nobody will ever post.
            #
            # `has_chart` is still True for the copy render below: in LIVE mode
            # `require_card` guarantees an accepted item carries a card (the
            # branch under it drops everything else), so previewing the copy with
            # has_chart=False would show the dry run a DIFFERENT variant family
            # than the one that ships. The card is deferred, not denied.
            card: dict[str, Any] = {"media": None, "published": {},
                                    "reason": "require_card disabled"}
            card_deferred = False
            if pt["require_card"]:
                if not live:
                    card_deferred = True
                    cards_deferred_dry_run += 1
                    card = {"media": None, "published": {},
                            "reason": "card-deferred-dry-run"}
                else:
                    # as_of = THE ROW'S SESSION, not the clock's `today` (defect
                    # 2). This argument is what the watchlist card prints in its
                    # header, so it is one of the three surfaces that must agree
                    # about which session the post is about — and a date the
                    # card takes from the wall clock is a claim nothing in the
                    # data supports. `cand_session` has just been proven equal
                    # to `today` by the row-session gate above, so this is a
                    # no-op in production TODAY; it is the derivation that
                    # matters, and _session_conflict below re-checks it rather
                    # than trusting the gate's ordering.
                    card = _resolve_card(cand, root=r, cfg=cfg or {},
                                         as_of=cand_session,
                                         now=now, slot=slot)
                    if not card.get("media"):
                        cards_unhosted += 1
                        dropped.append({
                            "reason": "no_card",
                            "detail": f"{lead_cashtag or cand['type']}: "
                                      f"{card.get('reason')}",
                        })
                        continue

            # ── Copy (reuse-only) ───────────────────────────────────────────
            try:
                text, headline, violations, bait = _render_copy_unbaited(
                    cand, account=chosen, voice=voice, persona=persona,
                    slot=slot,
                    has_chart=bool(card.get("media")) or card_deferred,
                    theme_cashtag_cap=int(pt["max_theme_cashtags_in_text"]))
            except Exception as exc:  # noqa: BLE001
                dropped.append({"reason": "copy_error", "detail": f"{lead_cashtag}: {exc}"})
                continue
            if bait:
                # Every variant this candidate could reach ended on a question
                # aimed at the reader. Reported, not shipped — the voice law is
                # not negotiable and a bank that is bait all the way down is a
                # copywriter defect to fix, not a post to make.
                dropped.append({"reason": "bait_tail",
                                "detail": f"{lead_cashtag or cand['type']}: "
                                          f"{_MAX_TAIL_ROLLS} variants all ended "
                                          f"on reader-bait"})
                continue
            if not text:
                dropped.append({"reason": "empty_copy", "detail": lead_cashtag})
                continue
            # Fail-closed: any validate_copy violation drops the candidate — there
            # is no operator at post time to catch bad copy.
            if violations:
                dropped.append({"reason": "copy_violation",
                                "detail": f"{lead_cashtag}: {violations[:3]}"})
                continue

            # ── OPTIONAL wire-register phrase pass (DEFAULT OFF) ────────────
            # Placed HERE, between the template's own validation and the gates
            # below, so whichever text wins faces every remaining gate. It can
            # only ever return the string it was handed or a phrase that cleared
            # `wire_violations` — and those laws are subset laws (no new number,
            # cashtag, link or session claim), so an accepted phrase cannot fail
            # a gate the template just passed. Disarmed, it is a dict build and a
            # return: no provider, no credential, no call, no latency.
            _phrased = phrase_or_template(
                text, facts=(cand.get("_mover_facts")
                             if cand["type"] == "mover"
                             else cand.get("_theme_facts")),
                kind=str(cand["type"]), now=now, cfg=cfg)
            llm_phrase_modes[_phrased["mode"]] = (
                llm_phrase_modes.get(_phrased["mode"], 0) + 1)
            text = _phrased["text"]

            # ── Cashtag breadth — EVERY KIND, theme_list included ────────────
            #
            # DEFECT 1: the exemption is gone. This gate used to read "(movers
            # only; theme_list exempt, per sentinel)", so the one kind that
            # enumerates a whole group by construction was the one kind nobody
            # counted — and the post that drew the operator's complaint shipped
            # eight cashtags in a single line ("$COHR $LITE $AXON $META $RBLX
            # $MSFT $GOOGL $U"), which is the spam fingerprint X flags. An
            # exemption granted to the format most likely to trip the rule is
            # not a policy; it is the rule pointed away from its own case.
            #
            # theme_list gets its OWN, tighter cap (max_theme_cashtags_in_text,
            # default 3 — the top of the operator's stated 2-3 band) and the
            # account's tier cap still applies on top: the STRICTER of the two
            # wins, so a ramping desk cannot be loosened by the theme knob and
            # the theme knob cannot be loosened by a graduated desk.
            #
            # This is measured on the RENDERED TEXT, not on the candidate's
            # cashtag list, because the text is what X reads. The card's own row
            # list is not text and is deliberately not counted here — see
            # _CARD_MAX_ROWS for why the picture may still carry all 8.
            max_cashtags = _acct_caps(chosen)["max_cashtags_per_post"]
            if cand["type"] == "theme_list":
                max_cashtags = min(int(max_cashtags),
                                   int(pt["max_theme_cashtags_in_text"]))
            distinct = set(_CASHTAG_RE.findall(text))
            if len(distinct) > max_cashtags:
                dropped.append({"reason": "cashtag_breadth",
                                "detail": f"{lead_cashtag or cand['type']}: "
                                          f"{len(distinct)} > {max_cashtags}"})
                continue

            # ── ONE SESSION PER POST ────────────────────────────────────────
            # The three surfaces (first line, body, card date) must all name the
            # session the ROWS are from. REJECTS, never warns — this lane
            # auto-approves and posts with no human in the loop, so a warning
            # here is a published post. See _session_conflict for the live
            # 2026-08-03 example this fires on ("up across the board today" +
            # "+3.7% on average on Friday" + a Monday card).
            _conflict = _session_conflict(
                text, now=now, row_session=cand_session,
                # The card's printed date IS `cand_session` by construction (it
                # is the argument passed to _resolve_card above). Passing it
                # through rather than assuming it is what makes the third
                # surface part of the check instead of part of the comment.
                card_session=cand_session)
            if _conflict:
                dropped.append({"reason": "session_conflict",
                                "detail": f"{lead_cashtag or cand['type']}: "
                                          f"{_conflict}"})
                continue

            # ── Near-dup gate (vs other accepted this run + existing today) ──
            tokset = sentinel._token_set(text)
            if any(sentinel._jaccard_sets(tokset, prev) >= near_dup_thresh
                   for prev in accepted_texts):
                dropped.append({"reason": "near_dup_run", "detail": lead_cashtag})
                continue
            if any(sentinel._jaccard_sets(tokset, prev) >= near_dup_thresh
                   for prev in existing_token_sets):
                dropped.append({"reason": "near_dup_today", "detail": lead_cashtag})
                continue

            # ── Build the outbox item + source stamp ────────────────────────
            source = _build_source(cand, slot, now, quote_source)
            try:
                item = outbox.make_item(
                    account=chosen,
                    kind=cand["type"],
                    text=text,
                    as_of=today,
                    # The hosted card. A rollup kind with no media[] is exactly
                    # what the bare-cashtag law quarantines, so this list is the
                    # difference between a publishable item and a dead one.
                    media=([card["media"]] if card.get("media") else None),
                    scheduled_at="immediate",
                    slot=f"LIVE-{slot}",
                    priority=6,   # operator-approved D1 items are priority 5 → sort first
                    provenance=_PROVENANCE,
                    source=source,
                    now=now,
                )
            except ValueError as exc:
                dropped.append({"reason": "make_item_invalid", "detail": f"{lead_cashtag}: {exc}"})
                continue

            # Commit account assignment BEFORE enqueue so a per-run second
            # candidate never targets the same desk even if enqueue duplicates.
            assigned_accounts.add(chosen)
            accepted_texts.append(tokset)

            if not live:
                would_generate.append({
                    "id": item["id"], "account": chosen, "kind": cand["type"],
                    "ticker": lead_ticker, "slot": f"LIVE-{slot}",
                    "text": text.replace("\n", " ")[:200],
                    # Per-row honesty: this preview carries NO media, because no
                    # card was drawn (see the dry-run branch above). A reader who
                    # sees `media: []` on a rollup kind must not conclude the
                    # live run would ship it bare — it would render the card
                    # first, and drop the candidate if that failed.
                    "card": "deferred_dry_run" if card_deferred else "n/a",
                })
                # Charge the account so the next candidate rotates onward in dry-run too.
                posted_today[chosen] = posted_today.get(chosen, 0) + 1
                existing_token_sets.append(tokset)
                existing_today.append(item)
                continue

            # Enqueue re-checks the cap against the day ledger; hand it the
            # CHOSEN account's tier-narrowed value so the two gates agree.
            result = outbox.enqueue(
                item, r,
                max_per_account_day=outbox.stricter_daily_cap(
                    cap, _acct_caps(chosen)["max_posts_per_account_per_day"]))
            if result == "queued":
                generated.append(item["id"])
                posted_today[chosen] = posted_today.get(chosen, 0) + 1
                existing_token_sets.append(tokset)
                existing_today.append(item)
            elif result in ("duplicate", "cross_account_duplicate"):
                # EXPECTED when the tape hasn't moved since the prior slot: the
                # identical text hashes to the same id. That idempotency is a
                # feature — report it quietly, don't treat it as an error.
                # cross_account_duplicate (XG-W2) is the same class of quiet
                # drop: another desk already carries near-identical copy, so
                # this one must not go out. Named explicitly rather than falling
                # into the generic failure branch, which would report a working
                # guard as an error.
                dropped.append({"reason": result, "detail": f"{lead_cashtag} ({item['id']})"})
            elif result == "cap_exceeded":
                dropped.append({"reason": "cap_exceeded", "detail": lead_cashtag})
                # Roll back the account reservation — nothing was written.
                assigned_accounts.discard(chosen)
                accepted_texts.pop()
            else:
                dropped.append({"reason": "enqueue_failed", "detail": f"{lead_cashtag}: {result}"})
                assigned_accounts.discard(chosen)
                accepted_texts.pop()

        if cards_unhosted:
            # Bare line-start print, NEVER through `log` — this module's logger
            # prefixes every record, and GitHub silently drops an annotation that
            # does not start the line. flush because stdout is block-buffered when
            # piped in Actions.
            print(f"::warning title=publish-time-card-unhosted::"
                  f"{cards_unhosted} publish-time mover/theme candidate(s) dropped "
                  f"in slot {slot}: the card would not render or host, and a post "
                  f"that names tickers ships a picture or does not ship",
                  flush=True)

        return {
            "enabled": True,
            "generated": generated,
            "would_generate": would_generate,
            "dropped": dropped,
            "quote_source": quote_source,
            "slot": slot,
            "cards_unhosted": cards_unhosted,
            # Always present (0 on a live run) so a report consumer can read it
            # unconditionally rather than .get()-ing around its absence.
            "cards_deferred_dry_run": cards_deferred_dry_run,
            # {} when the phrase pass never ran, {"off": N} when it is disarmed.
            "llm_phrase_modes": dict(llm_phrase_modes),
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content.generate_slot_items: %s", exc)
        return {
            "enabled": True,
            "generated": [],
            "would_generate": [],
            "dropped": [{"reason": "error", "detail": str(exc)}],
            "quote_source": "none",
            "slot": slot or "",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Small pure helpers used above
# ─────────────────────────────────────────────────────────────────────────────

def _item_full_text(item: dict) -> str:
    """The text used for near-dup — outbox items carry a single flat `text`."""
    return str(item.get("text") or "")


def _account_same_cashtag_today(existing_today: list[dict], account: str,
                                ticker: str, cashtag: str) -> int:
    """Count today's items on `account` whose source.ticker matches the candidate
    ticker OR whose text contains the candidate's lead cashtag (sentinel's
    per-account same-cashtag/day heuristic)."""
    tkr_u = str(ticker or "").upper()
    n = 0
    for it in existing_today:
        if it.get("account", "") != account:
            continue
        src_tkr = str((it.get("source") or {}).get("ticker") or "").upper()
        if tkr_u and src_tkr == tkr_u:
            n += 1
            continue
        if cashtag and cashtag in str(it.get("text") or ""):
            n += 1
    return n


def _build_source(cand: dict, slot: str, now: datetime, quote_source: str) -> dict[str, Any]:
    """The source stamp the live tape gate re-checks at post time.

    baseline_pct / ticker are what live_verify.verify_item re-verifies. For a
    mover that is the mover's ticker + its live pct. For a theme it is the LEAD
    MEMBER's ticker + pct (not the aggregate) — stamping the loudest number in
    the text makes the gate verify the exact figure a reader sees.
    """
    if cand["type"] == "mover":
        return {
            "lane": "publish_time",
            "slot_run": slot,
            "generated_at": _iso_now(now),
            "quote_source": quote_source,
            # The SESSION the rows belonged to, recorded so an audit can tell a
            # "today" claim from a re-dated one without re-deriving it.
            "session_asof": _cand_session(cand),
            "ticker": cand["ticker"],
            "baseline_pct": (cand.get("_mover_data") or {}).get("pct"),
        }
    out = {
        "lane": "publish_time",
        "slot_run": slot,
        "generated_at": _iso_now(now),
        "quote_source": quote_source,
        "session_asof": _cand_session(cand),
        "ticker": cand.get("_lead_ticker", ""),
        "baseline_pct": cand.get("_lead_pct"),
        "theme": cand.get("_theme_name", ""),
        "agg_pct": cand.get("_agg_pct"),
        # THE TAGGING ARM, and the receipt behind it. Stamped on EVERY theme item,
        # including the members-only ones — an arm label that only appears on the
        # treated arm gives post_metrics a treatment group and no control, which is
        # not a comparison. ADV is a proxy for X reach and not a measurement of it
        # (theme_proxy.adv20_musd), so this stamp is the only route from "the
        # bigger ticker should travel further" to something impressions can grade.
        "tag_arm": cand.get("_tag_arm", "members_only"),
    }
    proxy = cand.get("_tag_proxy")
    if proxy:
        out["tag_proxy"] = proxy
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Publish-time DAILY READ ("My read on today's move", kind=event)
# ─────────────────────────────────────────────────────────────────────────────
#
# Sibling to generate_slot_items, one family over. The NIGHTLY plan bakes the
# `event` post at ~04:00 UTC but schedules it after the close, so it ships a
# driver read written ~18h stale. This generates the read AT publish time from
# the FRESH daily brief (market_facts.event_facts reads why_the_tape_moved,
# which refreshes intraday), on the after-close ladder slot, ONCE per day.
#
# DARK BY DEFAULT: publish.publish_time_read.enabled is False when the block is
# absent, so old configs / test fixtures without the block never fire. When
# disabled the function returns a disabled report and writes NOTHING — nothing
# can auto-post under the default config.

def _after_close_slot() -> str:
    """The ladder's LAST rung — the after-close block the daily read fires in.

    DERIVED, never a literal. What this knob means is "the slot that owns the
    open-ended evening tail", which is always the final rung of
    outbox._LADDER_PT_TIMES — but it was written as a hardcoded label three
    times and went stale on two of the three ladder changes:
      * "S8"  (18:00 PT) under the retired 2-hour 8-slot ladder
      * "S19" (17:30 PT) under the 45-min 19-slot ladder — #3849 shipped
        against the 2-hour ladder minutes before #3855 replaced it
      * the 30-min 28-rung ladder (2026-07-28) made "S19" mean 13:00 PT, i.e.
        the middle of the trading day, and the read lane silently generated
        NOTHING because its gate never matched an after-close instant.
    A literal here is a landmine that only goes off when someone edits the
    ladder, which is exactly when nobody is looking at this file.
    """
    from engine.marketing import outbox  # noqa: PLC0415

    times = getattr(outbox, "_LADDER_PT_TIMES", None) or {}
    if not times:
        return "S19"  # fail-soft: the historical label, better than crashing
    # Last by clock time, not by dict order or label sort ("S9" > "S28" as text).
    return max(times.items(), key=lambda kv: (kv[1][0], kv[1][1]))[0]


# In-code defaults for the publish.publish_time_read block (mirror _DEFAULTS).
_READ_DEFAULTS: dict[str, Any] = {
    "enabled": False,       # DARK by default (operator arms after dry-runs)
    # After-close ladder slot — resolved from the ladder at call time by
    # _read_cfg so it tracks any future ladder change automatically.
    "slot": "",
}

_READ_KIND = "event"


def _read_cfg(cfg: dict | None) -> dict[str, Any]:
    """Resolve publish.publish_time_read over the in-code defaults (fail-soft).

    Mirrors _pt_cfg: a missing block leaves `enabled` False (the dark default),
    and a junk value coerces to the default type rather than raising.
    """
    out = dict(_READ_DEFAULTS)
    out["slot"] = _after_close_slot()
    try:
        block = ((cfg or {}).get("publish") or {}).get("publish_time_read") or {}
        for k, dv in _READ_DEFAULTS.items():
            if k in block:
                if isinstance(dv, bool):
                    v = block[k]
                    out[k] = v if isinstance(v, bool) else (
                        str(v).strip().lower() in {"1", "true", "yes"})
                else:
                    out[k] = type(dv)(block[k])
    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content: bad publish.publish_time_read config "
                    "(%s) — using defaults", exc)
    return out


def _ladder_local(now: datetime) -> datetime | None:
    """`now` in the ladder's Pacific clock, or None if the tz database is absent.

    The after-close ladder is a PACIFIC-clock concept, so both the weekday gate
    and the slot gate must read the Pacific frame — an S19 (17:30 PT) evening instant is
    the NEXT UTC calendar day (Fri 18:00 PT == Sat 01:00 UTC), so a UTC-based
    weekday check would wrongly reject a legitimate Friday after-close read and
    wrongly admit a Sunday-evening one. zoneinfo keeps the Pacific→UTC offset
    DST-safe (never hardcode -7/-8).
    """
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415
        return now.astimezone(ZoneInfo(outbox._LADDER_TZ))
    except Exception:  # noqa: BLE001
        return None


def _ladder_slot_label(local: datetime) -> str | None:
    """Map a Pacific-LOCAL datetime to its 45-min ladder slot label (S1..S19).

    The daily read fires on an after-close ladder slot (config default S19 =
    17:30 PT), NOT on the AM/PM/EOD publish window `_slot_label` returns. Each
    slot owns [t, t+45min) per outbox._LADDER_PT_TIMES; the LAST slot owns the
    open-ended evening tail (17:30 PT to midnight) so every after-close sweep
    lands in it. Ported from outbox._LADDER_PT_HOURS (2-hour, S1..S8) after
    #3855 replaced that ladder and left this consumer referencing a name that
    no longer existed — the lane failed soft to a no-op on every sweep.
    """
    minutes = local.hour * 60 + local.minute
    ordered = sorted(outbox._LADDER_PT_TIMES.items(),
                     key=lambda kv: kv[1][0] * 60 + kv[1][1])
    last_slot = ordered[-1][0]
    best: str | None = None
    for slot, (h, m) in ordered:
        start = h * 60 + m
        end = start + 45 if slot != last_slot else 24 * 60
        if start <= minutes < end:
            best = slot
    return best


def _empty_read_report(slot: str | None, *, enabled: bool,
                       drop: list[dict] | None = None) -> dict:
    """Disabled/empty report for the read lane (mirror _empty_report shape,
    quote_source fixed to 'brief' since this lane reads the daily brief)."""
    return {
        "enabled": enabled,
        "generated": [],
        "would_generate": [],
        "dropped": drop or [],
        "quote_source": "brief",
        "slot": slot or "",
    }


def _read_top_fact(facts_data: dict | None) -> str:
    """The freshest 'What's driving today: …' line, or '' if the brief has none.

    event_facts falls back to macro_facts, which returns an EMPTY facts list when
    neither regime nor brief exists — so an empty/absent text means no usable
    driver read (→ dropped no_brief)."""
    for f in (facts_data or {}).get("facts") or []:
        txt = str(f.get("text") or "").strip()
        if txt:
            return txt
    return ""


def _queued_read_today(state: dict, today: str) -> set[str]:
    """Accounts that already have a publish-time-lane `event` item queued today
    (provenance publisher_live_movers, created today). Enforces once/day per
    account across sweeps — a second sweep in the same after-close block must not re-post.
    """
    out: set[str] = set()
    for it in (state.get("items") or {}).values():
        if it.get("provenance") != _PROVENANCE:
            continue
        if it.get("kind") != _READ_KIND:
            continue
        if str(it.get("created_at") or "")[:10] == today:
            out.add(str(it.get("account") or ""))
    return out


def generate_read_item(
    root: Path | str,
    *,
    cfg: dict,
    now: datetime,
    state: dict,
    live: bool,
    account_filter: str | None = None,
) -> dict:
    """Generate the publish-time DAILY READ (kind=event) for the after-close slot.

    Returns a report dict with the SAME shape generate_slot_items returns:
    {enabled, generated:[ids], would_generate:[{account,kind,text}],
    dropped:[{reason,detail}], quote_source:"brief", slot}. NEVER raises — the
    whole body is fail-soft; on error it logs a warning and returns a report with
    the error noted. In dry-run (live=False) it writes NOTHING and fills
    would_generate; enqueues only when live is True.

    DARK GATE: when publish.publish_time_read.enabled is false (the default) it
    returns a disabled report immediately and writes nothing.
    """
    slot: str | None = None
    try:
        r = Path(root)
        rc = _read_cfg(cfg)

        # ── DARK GATE ───────────────────────────────────────────────────────
        if not rc["enabled"]:
            return _empty_read_report(None, enabled=False,
                                      drop=[{"reason": "disabled",
                                             "detail": "publish.publish_time_read.enabled is false"}])

        # ── Gate 1: weekday + configured after-close ladder slot ────────────
        # Both read the PACIFIC clock (see _ladder_local): the after-close slot
        # is a Pacific-clock concept and its UTC instant is the next calendar day.
        local = _ladder_local(now)
        if local is None:
            return _empty_read_report(None, enabled=True,
                                      drop=[{"reason": "no_tzdata",
                                             "detail": "zoneinfo tz database unavailable"}])
        if local.weekday() >= 5:  # Sat/Sun (Pacific)
            return _empty_read_report(None, enabled=True,
                                      drop=[{"reason": "not_weekday", "detail": local.strftime("%A")}])
        want_slot = str(rc["slot"] or "").strip().upper()
        slot = _ladder_slot_label(local)
        if slot != want_slot:
            # Not the after-close slot (or outside the ladder) → empty report so
            # the read fires ONCE/day, not on every sweep.
            return _empty_read_report(slot, enabled=True,
                                      drop=[{"reason": "wrong_slot",
                                             "detail": f"{slot or 'none'} != {want_slot}"}])

        # ── Fresh driver fact from the daily brief ──────────────────────────
        facts_data = market_facts.event_facts(r)
        top_fact = _read_top_fact(facts_data)
        if not top_fact:
            return _empty_read_report(slot, enabled=True,
                                      drop=[{"reason": "no_brief",
                                             "detail": "event_facts returned no usable driver read"}])

        today = now.strftime("%Y-%m-%d")

        # ── Eligible accounts (deterministic, config order) ─────────────────
        # Mirror generate_slot_items EXACTLY by sharing its helper: live accounts
        # (config `enabled` via the accounts model, overrides honoured), on this
        # lane's allowlist, holding a publish channel, matching account_filter.
        already_today = _queued_read_today(state, today)
        eligible = [
            acc for acc in _per_call_eligible(
                cfg, lane_key="publish_time_read", root=r,
                account_filter=account_filter)
            # once/day per account (spacing across sweeps)
            if str(acc.get("id", "")) not in already_today
        ]
        if not eligible:
            return _empty_read_report(slot, enabled=True,
                                      drop=[{"reason": "no_eligible_accounts",
                                             "detail": "no live, lane-allowed account has a publish channel (filter/already-posted)"}])

        dropped: list[dict] = []
        generated: list[str] = []
        would_generate: list[dict] = []

        for acc in eligible:
            aid = str(acc.get("id", ""))
            voice = acc.get("voice", "authoritative desk")
            persona = _persona_for(cfg or {}, aid, voice)

            # ── Copy: mirror content_studio's nightly event context exactly ──
            # (content_studio.py ~1713-1728). Non-ticker item → the deterministic
            # picker seeds variant rotation by CALENDAR DAY off ctx["as_of"] (the
            # #3824 fix), so a single daily read differs day to day. Feed the fresh
            # event_facts so {top_fact} is the "What's driving today: …" line.
            try:
                item_dict = {"type": _READ_KIND, "account": aid, "ticker": ""}
                ctx = copywriter.build_context(
                    item_dict, persona=persona or None, facts=facts_data or None)
                ctx["type"] = _READ_KIND
                ctx["voice"] = voice
                ctx["slot"] = f"LIVE-{slot}"
                ctx["as_of"] = today
                ctx["has_chart"] = False
                posts = copywriter.write_posts_deterministic([ctx])
                post = posts[0] if posts else {}
                headline = str(post.get("headline") or "")
                body = str(post.get("body") or "")
                text = (f"{headline}\n\n{body}" if headline and body
                        else (headline or body))
                violations = list(post.get("violations") or [])
            except Exception as exc:  # noqa: BLE001
                dropped.append({"reason": "copy_error", "detail": f"{aid}: {exc}"})
                continue
            if not text:
                dropped.append({"reason": "empty_copy", "detail": aid})
                continue
            # Fail-closed: any validate_copy violation drops the candidate — there
            # is no operator at post time to catch bad copy.
            if violations:
                dropped.append({"reason": "copy_violation",
                                "detail": f"{aid}: {violations[:3]}"})
                continue

            # ── Source stamp (the read carries the brief driver, no tape pct) ─
            source = {
                "lane": "publish_time",
                "slot_run": slot,
                "generated_at": _iso_now(now),
                "quote_source": "brief",
                "driver": top_fact,
            }
            try:
                item = outbox.make_item(
                    account=aid,
                    kind=_READ_KIND,
                    text=text,
                    as_of=today,
                    scheduled_at="immediate",
                    slot=f"LIVE-{slot}",
                    priority=6,
                    provenance=_PROVENANCE,
                    source=source,
                    now=now,
                )
            except ValueError as exc:
                dropped.append({"reason": "make_item_invalid", "detail": f"{aid}: {exc}"})
                continue

            if not live:
                would_generate.append({
                    "id": item["id"], "account": aid, "kind": _READ_KIND,
                    "ticker": "", "slot": f"LIVE-{slot}",
                    "text": text.replace("\n", " ")[:200],
                })
                continue

            result = outbox.enqueue(item, r)
            if result == "queued":
                generated.append(item["id"])
            elif result in ("duplicate", "cross_account_duplicate"):
                # EXPECTED if the brief hasn't changed since a prior sweep: the
                # identical text hashes to the same id (idempotent). The cross-
                # night dedup in enqueue (#3824) likewise catches a same-week
                # identical repeat, and the cross-ACCOUNT radar (XG-W2) catches
                # another desk already carrying near-identical copy. All three
                # are guards doing their job — report quietly, not as an error.
                dropped.append({"reason": result, "detail": f"{aid} ({item['id']})"})
            else:
                dropped.append({"reason": "enqueue_failed", "detail": f"{aid}: {result}"})

        return {
            "enabled": True,
            "generated": generated,
            "would_generate": would_generate,
            "dropped": dropped,
            "quote_source": "brief",
            "slot": slot,
        }

    except Exception as exc:  # noqa: BLE001
        log.warning("publish_time_content.generate_read_item: %s", exc)
        return {
            "enabled": True,
            "generated": [],
            "would_generate": [],
            "dropped": [{"reason": "error", "detail": str(exc)}],
            "quote_source": "brief",
            "slot": slot or "",
        }
