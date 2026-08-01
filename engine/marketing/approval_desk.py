"""engine/marketing/approval_desk.py — the AUTONOMOUS APPROVAL DESK.

THE DEFECT THIS CLOSES. The planned kinds (signal, chart, education, macro,
receipt, watchlist, event, congress, insider) have had NO functioning path to
live. The designed path was operator approval: the admin UI writes an
approve/hold row to `data/marketing/outbox/decisions.jsonl`, and
`outbox.apply_decisions` turns an `approve` into a `queued → approved`
transition. That file has ZERO rows in repo history. Every planned post that
ever reached X was hand-transitioned by an agent session. Meanwhile
`publish.auto_approve_scope: kinds` deliberately confines the publisher's
auto-approve pass to the publish-time lane (`provenance:
publisher_live_movers`), so the nightly desk writes into a queue that nothing
drains.

The operator's standing instruction is the specification, verbatim: "closely
audit them, then approve them so they go out quickly without me". This module
is that sentence as a machine gate — a set of NAMED checks, each of which can
be pointed at afterwards, that either clears an item to `approved`, kills it to
`quarantined` with the evidence in the note, or LEAVES IT ALONE for a human.

THE THREE VERDICTS, AND WHY THE THIRD ONE EXISTS.

  * every check passes                → `queued → approved`, actor
    `approval-desk`, note listing the checks that passed. The publisher's own
    dispatch gates (live tape, cap, cadence, chart law, near-dup, voice) all
    still run afterwards; this desk is an ADDITIONAL bar, never a bypass.
  * a HARD FAIL                       → `queued → quarantined` with
    `approval-desk: <check>: <one-line evidence>`. Terminal, on purpose: the
    named failures are all "this post asserts something the desk cannot stand
    behind", and a post that invents a level does not get better by waiting.
  * UNVERIFIABLE                      → nothing at all. The item stays `queued`
    and is counted as held for human review.

The third verdict is the whole safety argument. Autonomy that approves what it
cannot verify is worse than no autonomy: the operator loses both the review and
the signal that a review was needed. Every check therefore distinguishes "I
looked and it is wrong" from "I have nothing to look at", and only the first
one is allowed to be terminal.

WHAT THE DESK DELIBERATELY DOES NOT TOUCH.
  * `breaking` — it already has a working all-gates-passed path (the press /
    hot-tape immediate rail plus `--post-now`), and its TTL is measured in
    minutes; a desk that audits it would only slow it down.
  * `mover` / `theme_list` — kind-scoped auto-approve already clears these
    (`publish.auto_approve_kinds` + the publish-time lane), and they are
    generated seconds before dispatch from live quotes.
  * `wire`, `earnings`, `reply`, `news` — their lanes own their own admission.
  * anything a human has decided on. See `_human_has_spoken`.

CONFIG (`config/marketing.yml`, block `approval_desk`). `enabled` ships TRUE:
the operator asked for the autonomy explicitly, so the kill switch is the
config line, not the default. Everything else is a bound, not a feature flag.

Fail-soft throughout, at the item AND the sweep level: an exception while
auditing one item leaves that item queued (the conservative verdict) and the
sweep continues; an exception in the sweep leaves the whole queue untouched.
A desk that crashes must degrade to the pre-desk world (nothing gets approved),
never to an unaudited approval.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

#: The kinds this desk polices. The nine planned kinds — i.e. everything
#: `outbox.planned_kinds()` returns — because every one of them was written by
#: the nightly content plan into a queue with no drain.
#:
#: `education` IS here. The build brief's prose list names eight kinds and omits
#: it, but its own acceptance gate requires "the zero-payload education shape"
#: to quarantine by name, and an item of a kind the desk skips can never
#: quarantine at all. Education is also the kind that PRODUCED the zero-payload
#: defect ("Macro without the jargon", "The discipline a watch list enforces" —
#: bare template stems with no fact in them, five of the twelve value-gate
#: abstentions in the 154-emission corpus). Skipping it would exempt the exact
#: shape this desk exists to catch.
_DESK_KINDS_DEFAULT: tuple[str, ...] = (
    "signal", "chart", "education", "macro", "receipt",
    "watchlist", "event", "congress", "insider",
)

#: Per-sweep approval ceiling. NOT a rate limit on quality — a trickle valve.
#: A night where the nightly emits ~200 planned items across seven desks (the
#: measured plan size is 218) and every one of them clears would otherwise hand
#: the dispatch loop a 200-item approved backlog in a single sweep. The per
#: account daily cap and the global spacing floor would then meter it out over
#: days, which means the queue's ORDER decides what ships and the freshest
#: reads sit behind the stalest ones. Approving 40 per sweep against a ~30
#: sweep day keeps the approved pool roughly the size the dispatch lane can
#: actually drain, and the overflow is re-audited next sweep against fresher
#: evidence rather than sitting pre-blessed.
_MAX_APPROVALS_DEFAULT = 40

#: Same-account near-dup bar for the desk's own dedup check, per the build
#: brief. DELIBERATELY LOOSER than the publisher's post-time near-dup gate
#: (`outbox._NEAR_DUP_JACCARD` = 0.7), which still runs on every item this desk
#: approves. Two gates, two jobs: at 0.85 the desk refuses to APPROVE only the
#: obvious repeats (a post that is textually the same story as one sent this
#: week), and the tighter 0.7 gate remains the last word before the network.
#: Setting the desk to 0.7 would just move the same quarantine earlier and
#: strip the post-time gate of anything to do.
_DEDUP_JACCARD_DEFAULT = 0.85

#: Max |target / quoted price - 1| a swing-horizon post may print, in percent.
#:
#: EVERY KIND THIS DESK POLICES IS SWING-HORIZON. The house horizon is 2-4 weeks
#: (see the backtest horizon law); the intraday kinds — mover, theme_list,
#: breaking — are all explicitly out of the desk's scope, so there is no
#: horizon to branch on and the bound applies to every target the desk sees.
#: 35% over 2-4 weeks is already an extraordinary claim for a large-cap swing
#: read; past it the number is almost always a chart fact (a 52-week high, a
#: prior cycle peak) that the writer promoted into a price objective.
_MAX_TARGET_MOVE_PCT_DEFAULT = 35.0

#: Liveness TTL. Defaults to `outbox._STALE_QUEUED_HOURS` (36h) so the desk's
#: bar and the nightly reaper's bar are ONE number by default — see
#: `check_liveness` for the division of labour between them.
_TTL_HOURS_DEFAULT = 36.0


def _as_bool(v: Any, default: bool) -> bool:
    """Strict bool parse — a quoted "false" in YAML must not read as enabled."""
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(v: Any, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return f


def desk_config(cfg: dict | None) -> dict[str, Any]:
    """The `approval_desk` block, defaulted. The SINGLE reader of that config.

    A missing block is not "off": it yields the shipped defaults, `enabled`
    included. Deleting the key cannot silently disarm a desk the operator asked
    for — the same posture `outbox.llm_required` takes about the no-fallback
    law. Turning the desk off is an explicit `enabled: false`.
    """
    block = (cfg or {}).get("approval_desk") if isinstance(cfg, dict) else None
    if not isinstance(block, dict):
        block = {}

    kinds_raw = block.get("kinds")
    if isinstance(kinds_raw, (list, tuple)) and kinds_raw:
        kinds = frozenset(str(k).strip() for k in kinds_raw if str(k).strip())
    else:
        kinds = frozenset(_DESK_KINDS_DEFAULT)

    ttl_by_kind: dict[str, float] = {}
    raw_by_kind = block.get("ttl_hours_by_kind")
    if isinstance(raw_by_kind, dict):
        for k, v in raw_by_kind.items():
            f = _as_float(v, -1.0)
            if f >= 0:
                ttl_by_kind[str(k).strip()] = f

    try:
        max_approvals = int(block.get("max_approvals_per_sweep",
                                      _MAX_APPROVALS_DEFAULT))
    except (TypeError, ValueError):
        max_approvals = _MAX_APPROVALS_DEFAULT

    return {
        "enabled": _as_bool(block.get("enabled"), True),
        "max_approvals_per_sweep": max(max_approvals, 0),
        "kinds": kinds,
        "ttl_hours": _as_float(block.get("ttl_hours"), _TTL_HOURS_DEFAULT),
        "ttl_hours_by_kind": ttl_by_kind,
        "dedup_jaccard": _as_float(block.get("dedup_jaccard"),
                                   _DEDUP_JACCARD_DEFAULT),
        "max_target_move_pct": _as_float(block.get("max_target_move_pct"),
                                         _MAX_TARGET_MOVE_PCT_DEFAULT),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Check results
# ─────────────────────────────────────────────────────────────────────────────

#: A check either passed, hard-failed (terminal), or could not be evaluated.
PASS = "pass"
FAIL = "fail"          # terminal — quarantine
HOLD = "hold"          # soft — leave queued, someone/something else may heal it
UNVERIFIABLE = "unverifiable"   # no evidence to judge against — leave queued


class Check(NamedTuple):
    """One named check's verdict on one item.

    ``name`` is what lands in the ledger note, so it is the operator's handle on
    "why did the desk do that": it is a stable slug (`payload`,
    `invented_level`, `implausible_target`, `expired`, `chart_law`,
    `banned_language`, `near_dup`), never a sentence.
    """
    name: str
    status: str
    evidence: str = ""


class Verdict(NamedTuple):
    """The desk's decision on one item.

    ``action`` ∈ approve | quarantine | hold. ``check`` names the deciding
    check (empty on an approve). ``passed`` lists the checks that cleared, in
    evaluation order, and is what the approve note joins.
    """
    action: str
    check: str
    evidence: str
    passed: tuple[str, ...]
    checks: tuple[Check, ...]


# ─────────────────────────────────────────────────────────────────────────────
# Check 1 — payload
# ─────────────────────────────────────────────────────────────────────────────

#: `$ALL`, `$BRK.B`. Same shape the publisher's bare-cashtag gate uses.
_CASHTAG_RE = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z])?\b")

#: Any digit run — the loosest possible reading of "a number", on purpose. The
#: payload check is a FLOOR, not a quality bar: it asks whether the post carries
#: anything falsifiable at all. Tightening it here would start rejecting posts
#: that number_sanity is the right place to judge.
_DIGIT_RE = re.compile(r"\d")

#: A dated precedent: "since May 20", "in 2019", "2026-07-24", "last March".
#: Month names (full and abbreviated) and 4-digit years in the plausible market
#: range. A bare year also matches _DIGIT_RE, so this exists mostly for the
#: month-name form, which carries a precedent with no digits in it at all
#: ("the setup that worked last October").
_DATED_PRECEDENT_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)


def check_payload(text: str) -> Check:
    """A post must carry at least one concrete payload token. HARD FAIL.

    THE ZERO-PAYLOAD EDUCATION DEFECT, ENFORCED AT POST TIME FOREVER. The
    measured shapes were "Macro without the jargon", "The discipline a watch
    list enforces", "The base-rate way of thinking", "Using analogues without
    kidding yourself" — a hook, a promise of a lesson, and nothing a reader
    could check, disagree with, or act on. They cleared every gate in the stack
    because every gate in the stack screens what a post SAYS (banned words,
    invented levels, stale quotes) and none of them screened whether it said
    anything.

    A payload token is a number, a cashtag, or a dated precedent. That is a
    deliberately low bar: it is not "is this post good", it is "does this post
    make a claim". The value gate judges quality; this judges existence, and it
    is terminal because a hook with no payload cannot be repaired by waiting —
    there is no missing number that a later sweep will supply.
    """
    src = str(text or "")
    found: list[str] = []
    if _DIGIT_RE.search(src):
        found.append("number")
    if _CASHTAG_RE.search(src):
        found.append("cashtag")
    if _DATED_PRECEDENT_RE.search(src):
        found.append("dated precedent")
    if found:
        return Check("payload", PASS, "+".join(found))
    return Check(
        "payload", FAIL,
        f"no number, cashtag or dated precedent in {len(src)} chars of copy: "
        f"{src.strip()[:90]!r}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — number_sanity (evidence resolution + the two hard fails)
# ─────────────────────────────────────────────────────────────────────────────

#: The item['source'] keys that ARE forward price levels, mapped to the ctx
#: keys `copywriter.allowed_level_tokens` reads.
#:
#: PER-KIND EVIDENCE RESOLUTION, MEASURED. A census of the 236 rows in
#: `data/marketing/outbox/items.jsonl` says exactly what each kind's `source`
#: carries, and it is much thinner than the emit code reads:
#:
#:   signal     ticker(22/22) chart_id(22) signal_id(16) direction/entry/
#:              invalidation(16) media_url(15) value_gate(17)
#:   chart      ticker(26/26) chart_id(26) signal_id/direction/entry/
#:              invalidation(15) media_png_path(24) value_gate(24)
#:   watchlist  ticker(93/93) direction(56) entry/invalidation/signal_id(34)
#:              state/last_close/wk_pct(22, the weekend_levels lane) value_gate(73)
#:   macro      plan_item_id chart_id value_gate — NO NUMERIC EVIDENCE
#:   education  plan_item_id chart_id value_gate — NO NUMERIC EVIDENCE
#:   event      plan_item_id chart_id value_gate — NO NUMERIC EVIDENCE
#:   insider    plan_item_id chart_id ticker     — NO NUMERIC EVIDENCE
#:   congress   (no rows in the corpus)
#:   receipt    (no rows in the corpus)
#:
#: `t1` and `t2` are NOT stamped by any emitter today — `emit_from_content_plan`
#: copies only direction/entry/invalidation off the plan block. They are read
#: here anyway, defensively, so the day an emitter starts stamping them the
#: desk widens by itself instead of quarantining the new levels as invented.
_LEVEL_SOURCE_KEYS: tuple[tuple[str, str], ...] = (
    ("entry", "entry_str"),
    ("t1", "t1_str"),
    ("t2", "t2_str"),
    ("invalidation", "inv_str"),
    ("stop", "stop_str"),
    ("target", "target_str"),
)

#: Non-level numeric evidence: numbers the item's own packet asserts, which
#: license a number in the copy without licensing it as a TARGET.
_PACKET_NUMBER_KEYS: tuple[str, ...] = (
    "baseline_pct", "last_close", "wk_pct", "agg_pct", "marker_price",
)

#: "at 43.91", "$LPG at 43.91" — the price the post itself quotes. Last resort
#: for the implausible-target check when the item carries no entry or close.
_QUOTED_PRICE_RE = re.compile(
    r"\bat\s+\$?(\d+(?:,\d{3})*(?:\.\d+)?)\b(?!\s*%)", re.IGNORECASE)


def _finite(v: Any) -> float | None:
    try:
        f = float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def item_evidence(item: dict, *, plan_charts: dict | None = None) -> dict[str, Any]:
    """Everything numeric this item can prove about itself.

    Returns a dict shaped as the ctx `copywriter.invented_level_violations`
    reads (`entry_str` / `t1_str` / `t2_str` / `inv_str` / `stop_str` /
    `target_str` / `numbers_whitelist`), plus `quoted_price` and `sources`
    (which resolution steps actually fired — this is what the ledger note
    quotes, so a quarantine can be argued with).

    RESOLUTION LADDER, widest to narrowest:
      1. `source.entry` / `.invalidation` / (`.t1` / `.t2` / `.stop` /
         `.target` when a future emitter stamps them) — the plan's own forward
         levels, and the ONLY thing that licenses a price objective.
      2. `source.baseline_pct` / `.last_close` / `.wk_pct` / `.agg_pct` — the
         packet's own asserted numbers. These license a number in the copy but
         NEVER a target: promoting a fact to a price objective is precisely the
         $TPR-228 fabrication `invented_level_violations` was written for.
      3. `plan_charts[source.chart_id].marker_price` — the chart's marked
         price, when `data/marketing/content_plan.json` is readable and the
         chart id back-joins. Same tier as (2): a fact, not an objective.
      4. `source.fact_packet` numbers, when a lane stamps one (the breaking
         lane does; no planned lane does today).

    NOTE WHAT IS ABSENT. `numbers_whitelist` — the full list of numbers the
    writer was licensed to type — is built in `copywriter.build_context`, lives
    in the generation-time ctx, and is stamped onto NOTHING. The value-gate
    metadata on real items says so in its own words: `numbers_whitelist_
    supplied: false`. That is why this desk does not hard-fail an ordinary
    number that fails to trace: with no whitelist on the item, a strict
    every-token rule would quarantine the entire planned queue for a defect of
    the EMIT path rather than of the copy. It hard-fails LEVELS (which have
    real evidence when the item has any) and HOLDS everything else it cannot
    verify. See `check_number_sanity`.
    """
    src = item.get("source")
    src = src if isinstance(src, dict) else {}
    out: dict[str, Any] = {}
    sources: list[str] = []

    for skey, ctx_key in _LEVEL_SOURCE_KEYS:
        val = src.get(skey)
        if val is None:
            continue
        f = _finite(val)
        if f is None:
            continue
        out[ctx_key] = f"{f}"
        sources.append(f"source.{skey}")

    whitelist: list[str] = []
    for key in _PACKET_NUMBER_KEYS:
        f = _finite(src.get(key))
        if f is None:
            continue
        whitelist.append(f"{f}")
        sources.append(f"source.{key}")

    chart_id = str(src.get("chart_id") or "").strip()
    if chart_id and isinstance(plan_charts, dict):
        chart = plan_charts.get(chart_id)
        if isinstance(chart, dict):
            f = _finite(chart.get("marker_price"))
            if f is not None:
                whitelist.append(f"{f}")
                sources.append(f"plan_charts[{chart_id}].marker_price")

    packet = src.get("fact_packet")
    if isinstance(packet, dict):
        for n in (packet.get("numbers_whitelist") or []):
            whitelist.append(str(n))
        if packet.get("numbers_whitelist"):
            sources.append("source.fact_packet.numbers_whitelist")

    out["numbers_whitelist"] = whitelist

    # The price the post is measured against. Item evidence first (an entry or
    # a close is what the plan actually believed), then the chart marker, then
    # the copy's own "at <price>" anchor — which is weaker evidence but is
    # exactly what a reader sees, so a target measured against it is measured
    # against the claim the post makes.
    quoted = None
    for cand in (out.get("entry_str"), src.get("last_close")):
        quoted = _finite(cand)
        if quoted is not None:
            break
    if quoted is None and chart_id and isinstance(plan_charts, dict):
        chart = plan_charts.get(chart_id)
        if isinstance(chart, dict):
            quoted = _finite(chart.get("marker_price"))
    if quoted is None:
        m = _QUOTED_PRICE_RE.search(str(item.get("text") or ""))
        if m:
            quoted = _finite(m.group(1))
    out["quoted_price"] = quoted
    out["sources"] = sources
    out["has_levels"] = any(k in out for _, k in _LEVEL_SOURCE_KEYS)
    out["has_evidence"] = bool(out["has_levels"] or whitelist)
    return out


def _target_tokens(text: str) -> list[str]:
    """Numbers the copy asks the reader to AIM at. Reuses the copywriter's own
    target regexes, so "toward 228", "then 260" and "T1 190" are read here
    exactly as the generation-time gate reads them."""
    from engine.marketing.copywriter import (  # noqa: PLC0415
        _TARGET_LADDER_RE, _TARGET_SLOT_RE, _SLOT_NON_LEVEL_NOUNS,
    )
    src = str(text or "")
    out: list[str] = []
    for m in _TARGET_SLOT_RE.finditer(src):
        nxt = re.match(r"\s*([A-Za-z']+)", src[m.end():])
        if nxt and nxt.group(1).lower() in _SLOT_NON_LEVEL_NOUNS:
            continue
        if m.group(1) not in out:
            out.append(m.group(1))
        pos = m.end()
        while True:
            step = _TARGET_LADDER_RE.match(src[pos:])
            if not step:
                break
            after = re.match(r"\s*([A-Za-z']+)", src[pos + step.end():])
            if not (after and after.group(1).lower() in _SLOT_NON_LEVEL_NOUNS):
                if step.group(1) not in out:
                    out.append(step.group(1))
            pos += step.end()
    return out


def check_number_sanity(item: dict, ev: dict, *,
                        max_target_move_pct: float = _MAX_TARGET_MOVE_PCT_DEFAULT,
                        ) -> Check:
    """Every level the copy prints must trace to the item's own fact evidence.

    THREE OUTCOMES, and the difference between them is the safety argument:

      * `implausible_target` (HARD FAIL) — a printed target more than
        ±max_target_move_pct from the price the post quotes. Checked FIRST and
        independently of the whitelist, because a target can be perfectly
        traceable and still be a fabrication: the $LPG post "at 43.91 …
        Target 68.41" is +55.8% over a 2-4 week horizon, which is not a swing
        read, it is a lottery ticket wearing one.
      * `invented_level` (HARD FAIL) — a target or price-slot number the item's
        own levels/packet never carried, via
        `copywriter.invented_level_violations` (the $TPR-228 gate: a legitimate
        52-week-high FACT promoted into a price objective) plus
        `copywriter.price_slot_tokens` for the entry/stop/below slots that gate
        does not read. Only reachable when the item HAS evidence — see below.
      * UNVERIFIABLE — the item carries no numeric evidence at all and the copy
        prints numbers. Nothing to check against, so the desk does not approve
        and does not kill: it leaves the item for a human. This is the honest
        verdict for macro / education / event / insider items, whose `source`
        (measured, see `_LEVEL_SOURCE_KEYS`) carries no numbers whatsoever.

    A number that is neither a level nor in a slot is NOT hard-failed even when
    it fails to trace. `numbers_whitelist` is never stamped onto an outbox item
    (`value_gate.components.numbers_whitelist_supplied: false` on real rows), so
    a strict every-token rule would quarantine the whole planned queue for a
    gap in the EMIT path. When the item has no evidence those numbers land in
    the UNVERIFIABLE branch, which is where an unprovable claim belongs.
    """
    from engine.marketing.copywriter import (  # noqa: PLC0415
        invented_level_violations, price_slot_tokens,
    )
    text = str(item.get("text") or "")

    # 1. Implausible target — independent of the whitelist, needs only a price.
    quoted = ev.get("quoted_price")
    targets = _target_tokens(text)
    if quoted is not None and quoted > 0:
        for tok in targets:
            tgt = _finite(tok)
            if tgt is None:
                continue
            move_pct = (tgt / quoted - 1.0) * 100.0
            if abs(move_pct) > max_target_move_pct:
                return Check(
                    "implausible_target", FAIL,
                    f"target {tok} is {move_pct:+.1f}% from the quoted price "
                    f"{quoted:g} (swing horizon bar is "
                    f"±{max_target_move_pct:g}%)",
                )

    # 2. Invented level — only meaningful when there IS a packet to contradict.
    slot_tokens = price_slot_tokens(text)
    if not ev.get("has_evidence"):
        if slot_tokens or targets or _DIGIT_RE.search(text):
            return Check(
                "number_sanity", UNVERIFIABLE,
                f"item carries no fact evidence (source keys: "
                f"{sorted((item.get('source') or {}).keys()) or 'none'}) and the "
                f"copy prints {len(slot_tokens) + len(targets)} level(s) / "
                f"numbers",
            )
        return Check("number_sanity", PASS, "no numbers to trace")

    viols = invented_level_violations(text, ev)
    if viols:
        return Check("invented_level", FAIL, str(viols[0])[:200])

    # `invented_level_violations` reads only the TARGET slots. The entry / stop
    # / below / above slots are the other half of the same law, and the
    # copywriter already knows how to find them.
    #
    # DELIBERATELY A WIDER ALLOWED SET THAN THE TARGET GATE USES. A target is a
    # forward objective and may come only from the plan's levels — that
    # strictness is the $TPR-228 lesson and it stays. The other price slots
    # carry the post's OWN QUOTE ("$LPG at 43.91", "holding above 41.25"),
    # which is a description of the tape, not an ask. Judging those against the
    # levels alone would quarantine every post that states the price it is
    # talking about, so the packet numbers and the resolved quote anchor count
    # here. What is left is the real defect: a number in a price slot that
    # matches NOTHING the item can prove — no level, no packet fact, not even
    # the price the post itself quotes.
    from engine.marketing.copywriter import allowed_level_tokens  # noqa: PLC0415
    allowed = set(allowed_level_tokens(ev))
    allowed |= {str(n) for n in (ev.get("numbers_whitelist") or [])}
    for n in list(allowed):
        f = _finite(n)
        if f is not None:
            allowed.add(f"{f:.2f}")
            allowed.add(f"{f:g}")
    if quoted is not None:
        allowed.add(f"{quoted:.2f}")
        allowed.add(f"{quoted:g}")
    for tok in slot_tokens:
        f = _finite(tok)
        if tok in allowed:
            continue
        if f is not None and (f"{f:.2f}" in allowed or f"{f:g}" in allowed):
            continue
        return Check(
            "invented_level", FAIL,
            f"level '{tok}' sits in a price slot but is not one of this item's "
            f"levels or packet numbers ({', '.join(sorted(allowed)) or 'none'}); "
            f"evidence from {', '.join(ev.get('sources') or []) or 'nothing'}",
        )

    return Check("number_sanity", PASS,
                 f"traced to {', '.join(ev.get('sources') or []) or 'no levels'}")


# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — liveness
# ─────────────────────────────────────────────────────────────────────────────

def check_liveness(item: dict, *, now: datetime, ttl_hours: float,
                   ttl_hours_by_kind: dict[str, float] | None = None) -> Check:
    """A post whose slot is more than its TTL in the past is about a dead tape.

    THE DIVISION OF LABOUR WITH THE EXISTING REAPERS — this check fills a gap,
    it does not duplicate one.

      * `outbox.expire_stale_planned` (36h) already retires planned items, but
        ONLY `provenance == content_studio` and only at NIGHTLY EMIT time. The
        desk's sweep runs it too (see `run`), which is itself the first half of
        the gap: nothing ran it during the trading day.
      * `outbox.expire_stale_wire` (3h/12h by kind) covers the fast lanes'
        `scheduled_at == "immediate"` rows. Every kind it takes is out of this
        desk's scope.
      * NEITHER covers a planned-kind item from any OTHER provenance. The
        measured example is the whole `weekend_levels` watchlist lane (22 rows
        carrying state / last_close / wk_pct): planned kind, real ladder slot,
        swept by nobody. That is what this check retires.

    So: an item the nightly reaper already covers has, by the time we get here,
    either been retired by the `expire_stale_planned` call in `run` or is
    inside the TTL — and re-checking it is a cheap no-op. An item from another
    provenance gets its first and only liveness check right here.

    A per-kind TTL is honoured when configured (`ttl_hours_by_kind`), and ships
    EMPTY: the desk's default bar is exactly the reaper's 36h, so nothing about
    liveness changes for a covered item until an operator says otherwise. A
    kind TTL is only meaningful when it is STRICTER, since the reaper has
    already taken anything past 36h in the covered set.

    An unparseable or absent `scheduled_at` is never expired — a malformed
    stamp must not be the reason a post is destroyed, the rule
    `outbox._wire_item_born_at` states in the same words.
    """
    kind = str(item.get("kind") or "")
    ttl = float((ttl_hours_by_kind or {}).get(kind, ttl_hours))
    if ttl <= 0:
        return Check("liveness", PASS, "TTL disabled")
    raw = str(item.get("scheduled_at") or "").strip()
    if not raw or raw == "immediate":
        return Check("liveness", PASS, "no ladder slot to be late for")
    try:
        sched = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return Check("liveness", PASS, f"unparseable scheduled_at {raw!r}")
    if sched.tzinfo is None:
        sched = sched.replace(tzinfo=timezone.utc)
    age_h = (now - sched).total_seconds() / 3600.0
    if sched < now - timedelta(hours=ttl):
        return Check(
            "expired", FAIL,
            f"slot {raw} is {age_h:.1f}h old, past the {ttl:g}h TTL for "
            f"kind {kind!r} — the tape it describes is gone",
        )
    return Check("liveness", PASS, f"{age_h:.1f}h past slot, inside {ttl:g}h")


# ─────────────────────────────────────────────────────────────────────────────
# Check 4 — chart_law
# ─────────────────────────────────────────────────────────────────────────────

def _chart_bearing_kinds() -> frozenset[str]:
    """The publisher's own chart-law kind sets, resolved at call time.

    Imported from `scripts.marketing_publisher` so the two cannot drift:
    widening either set there widens this desk automatically. Lazy + fail-soft
    with a literal floor, the same shape `outbox.planned_kinds()` uses — the
    engine must not hard-depend on a script at import time.
    """
    try:
        from scripts.marketing_publisher import (  # noqa: PLC0415
            _CHART_BEARING_KINDS, _TICKER_ROLLUP_KINDS,
        )
        return frozenset(_CHART_BEARING_KINDS) | frozenset(_TICKER_ROLLUP_KINDS)
    except Exception:  # noqa: BLE001
        return frozenset({"signal", "chart", "watchlist", "receipt",
                          "theme_list", "mover"})


def _hosted_media_url(item: dict) -> str:
    """The item's public https media URL, "" when it has none.

    Reads the same two places the publisher reads: each `media[]` entry's
    `media_url`, and `source.media_url` (which `emit_from_content_plan` stamps
    so the publisher can attach without unpacking the media list). The backfill
    SIDECAR is deliberately not consulted — the desk's verdict here is a soft
    hold precisely because the sidecar may still heal the item before dispatch.
    """
    for m in (item.get("media") or []):
        if not isinstance(m, dict):
            continue
        u = str(m.get("media_url") or "").strip()
        if u.lower().startswith(("http://", "https://")):
            return u
    src = item.get("source")
    if isinstance(src, dict):
        u = str(src.get("media_url") or "").strip()
        if u.lower().startswith(("http://", "https://")):
            return u
    return ""


def check_chart_law(item: dict, *, media_enabled: bool = True) -> Check:
    """A ticker-bearing post owes a hosted picture. SOFT HOLD, never terminal.

    The operator's standing law is absolute about the outcome ("YOU WILL NOT
    SHIP THESE TEXT ONLY") and the publisher enforces it at dispatch. The
    desk's job is narrower: it must not APPROVE a post that has no picture yet.

    HOLD, NOT QUARANTINE, and the distinction is load-bearing. A missing
    `media_url` is usually an R2 upload race, and
    `scripts/marketing_media_backfill.py` exists to resolve it hours later —
    the publisher's own `_missing_required_media` defers for exactly that
    reason and only quarantines after `_MEDIA_DEFER_MAX_AGE_DAYS`. A desk that
    quarantined here would destroy a good post the backfill was about to heal,
    and it would do it terminally.

    INERT when `publish.media_enabled` is off: with the global gate down
    nothing can resolve a URL, so holding on it would wedge every ticker post
    rather than one — the same reasoning `_missing_required_media` states.
    """
    kind = str(item.get("kind") or "")
    if kind not in _chart_bearing_kinds():
        return Check("chart_law", PASS, f"kind {kind!r} owes no picture")
    if not media_enabled:
        return Check("chart_law", PASS, "publish.media_enabled off — gate inert")
    url = _hosted_media_url(item)
    if url:
        return Check("chart_law", PASS, "hosted media present")
    return Check(
        "chart_law", HOLD,
        f"ticker kind {kind!r} carries no hosted media_url yet — leaving queued "
        f"for the media backfill lane",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check 5 — banned_language
# ─────────────────────────────────────────────────────────────────────────────

def check_banned_language(item: dict) -> Check:
    """Re-scan the copy through the house lists. HARD FAIL.

    `copywriter.banned_language` and nothing else — the lists are never
    re-implemented here. THE QUEUE IS A BYPASS AROUND EVERY GENERATION LAW: the
    2026-07-27 "$AVGO POC held" post was written by a lane that predated the
    study-name bans and fired days later where no generation-time validator
    could reach it. The publisher already re-screens at dispatch for that
    reason; the desk screens at APPROVAL for the same one, so a violation is
    caught before it is blessed rather than after.
    """
    from engine.marketing.copywriter import banned_language  # noqa: PLC0415
    viols = banned_language(str(item.get("text") or ""))
    if viols:
        return Check("banned_language", FAIL,
                     f"{len(viols)} violation(s): {'; '.join(viols[:3])}"[:200])
    return Check("banned_language", PASS, "clean")


# ─────────────────────────────────────────────────────────────────────────────
# Check 6 — dedup
# ─────────────────────────────────────────────────────────────────────────────

def check_dedup(item: dict, posted_texts: dict[str, list[tuple[str, str, str]]],
                *, threshold: float = _DEDUP_JACCARD_DEFAULT) -> Check:
    """Near-identical to something this account already POSTED this week.

    Corpus and similarity are both reused, never re-implemented:
    `outbox.recent_posted_texts` (folded status posted/posting, 7-day window,
    per account, recalled items excluded because their text never reached
    anyone) and `outbox.token_jaccard`.

    Strictly per-account, like the publisher's post-time gate: one account
    rewording its own coverage is a style problem, two accounts converging is a
    network-linkage tell and that is sentinel's plan-time job at a stricter bar.
    """
    from engine.marketing.outbox import token_jaccard  # noqa: PLC0415
    text = str(item.get("text") or "")
    acct = str(item.get("account") or "")
    best_id, best_day, best = "", "", 0.0
    for prior_id, prior_text, prior_as_of in (posted_texts or {}).get(acct, []):
        score = token_jaccard(text, prior_text)
        if score > best:
            best_id, best_day, best = prior_id, prior_as_of, score
    if best >= threshold:
        return Check(
            "near_dup", FAIL,
            f"jaccard={best:.2f} vs {best_id} posted {best_day} (bar "
            f"{threshold:g}) — same content, not a deep rewording",
        )
    return Check("dedup", PASS,
                 f"max jaccard {best:.2f} vs {len((posted_texts or {}).get(acct, []))} "
                 f"recent post(s)")


# ─────────────────────────────────────────────────────────────────────────────
# The audit
# ─────────────────────────────────────────────────────────────────────────────

def audit_item(item: dict, *, now: datetime, posted_texts: dict | None = None,
               plan_charts: dict | None = None, media_enabled: bool = True,
               desk_cfg: dict | None = None) -> Verdict:
    """Run every named check on one item and return the desk's decision.

    PURE — no I/O, no ledger writes, no config reads beyond the dict handed in.
    That is what makes the behavioural matrix test possible: one item per
    verdict class, no fixtures on disk.

    CHECK ORDER is the brief's order (payload, number_sanity, liveness,
    chart_law, banned_language, dedup) and is part of the contract: the first
    HARD FAIL in that order is the one whose name lands in the ledger note, so
    the same item always gets the same reason. Every check still RUNS — the
    `checks` tuple carries all six — so the operator log can show the full
    picture even when only one name is recorded.

    RESOLUTION: any hard fail → quarantine. Else any hold/unverifiable →
    leave queued. Else → approve.
    """
    cfg = desk_cfg or desk_config(None)
    text = str(item.get("text") or "")
    ev = item_evidence(item, plan_charts=plan_charts)

    checks: list[Check] = [
        check_payload(text),
        check_number_sanity(item, ev,
                            max_target_move_pct=cfg["max_target_move_pct"]),
        check_liveness(item, now=now, ttl_hours=cfg["ttl_hours"],
                       ttl_hours_by_kind=cfg["ttl_hours_by_kind"]),
        check_chart_law(item, media_enabled=media_enabled),
        check_banned_language(item),
        check_dedup(item, posted_texts or {}, threshold=cfg["dedup_jaccard"]),
    ]

    for c in checks:
        if c.status == FAIL:
            return Verdict("quarantine", c.name, c.evidence,
                           tuple(x.name for x in checks if x.status == PASS),
                           tuple(checks))
    for c in checks:
        if c.status in (HOLD, UNVERIFIABLE):
            return Verdict("hold", c.name, c.evidence,
                           tuple(x.name for x in checks if x.status == PASS),
                           tuple(checks))
    return Verdict("approve", "", "",
                   tuple(x.name for x in checks), tuple(checks))


# ─────────────────────────────────────────────────────────────────────────────
# The sweep
# ─────────────────────────────────────────────────────────────────────────────

def _human_has_spoken(item_id: str, state: dict) -> bool:
    """True when the admin decisions path has already ruled on this item.

    THE decisions.jsonl PATH OUTRANKS THE DESK, IN BOTH DIRECTIONS. A `hold` is
    the operator saying "not yet" and the desk must never override it —
    `fold_state` already surfaces those as `held`, and this repeats the check
    off the raw decision row so a fold-shape change cannot silently disarm it.
    An `approve` is the operator's own clearance, which `apply_decisions` turns
    into the transition; the desk stepping in would race it and lose (the
    second transition is illegal and logs a warning). Either way the item is
    not the desk's business.
    """
    if item_id in (state.get("held") or set()):
        return True
    dec = (state.get("decisions") or {}).get(item_id)
    return bool(isinstance(dec, dict) and dec.get("decision"))


def _load_plan_charts(root: Path | str | None) -> dict[str, dict]:
    """`featured_charts` from content_plan.json, keyed by chart id. {} on any
    error — the chart marker is one rung of the evidence ladder, never a
    dependency: an unreadable plan costs the desk that rung and nothing else."""
    try:
        base = Path(root) if root else Path(".")
        path = base / "data" / "marketing" / "content_plan.json"
        plan = json.loads(path.read_text(encoding="utf-8"))
        charts = plan.get("featured_charts")
        if isinstance(charts, dict):
            return {str(k): v for k, v in charts.items() if isinstance(v, dict)}
        if isinstance(charts, list):
            return {str(c.get("id")): c for c in charts
                    if isinstance(c, dict) and c.get("id")}
    except Exception as exc:  # noqa: BLE001
        log.info("approval_desk: content_plan.json unavailable (%s) — chart "
                 "markers drop out of the evidence ladder", exc)
    return {}


def _empty_tally(status: str, reason: str = "") -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "approved": 0,
        "quarantined": 0,
        "held": 0,
        "capped": 0,
        "expired": 0,
        "considered": 0,
        "approved_ids": [],
        "quarantined_ids": [],
        "held_ids": [],
        "capped_ids": [],
        "by_check": {},
    }


def run(root: Path | str | None = None, *, cfg: dict | None = None,
        now: datetime | None = None, live: bool = False,
        account: str | None = None, media_enabled: bool = True,
        state: dict | None = None) -> dict[str, Any]:
    """Audit every eligible queued item and act. The sweep entry point.

    Returns a tally: `{status, approved, quarantined, held, capped, expired,
    considered, *_ids, by_check}`. `status` is `disabled` when the config kill
    switch is off and `ran` otherwise — the tally SAYS which, so a Floor row
    reading zeros can be told apart from a desk that never ran.

    DRY-RUN MAKES NO LEDGER WRITES. Same law as the publisher's auto-approve
    pass and its wire reaper: quarantine is terminal and a projection must not
    destroy the queue it is projecting. The tally still reports what the desk
    WOULD have done, which is how an operator reads a change before arming it.

    Never raises.
    """
    ts_now = now or datetime.now(timezone.utc)
    desk_cfg = desk_config(cfg)
    if not desk_cfg["enabled"]:
        return _empty_tally("disabled", "approval_desk.enabled is false")

    tally = _empty_tally("ran")
    try:
        from engine.marketing import outbox as _outbox  # noqa: PLC0415

        # ── Reuse the canonical planned reaper (the covered set) ─────────────
        # `expire_stale_planned` is the repo's one writer for "a planned item
        # sat past its slot", and until this call it ran ONLY at nightly emit.
        # Running it here is the gap-fill: the publish sweep runs on the ladder
        # all day, so a plan that goes stale at 10am no longer waits until
        # tonight to be retired. Its own scope (content_studio provenance,
        # scheduled_at present) is unchanged and unduplicated — everything it
        # does not cover falls to `check_liveness` below.
        if live:
            exp = _outbox.expire_stale_planned(
                root, now=ts_now, max_age_hours=int(desk_cfg["ttl_hours"]),
                actor="approval-desk")
            tally["expired"] = int(exp.get("expired") or 0)
            if tally["expired"]:
                state = None  # the fold below must see the retirements

        if state is None:
            state = _outbox.fold_state(root)
        items_by_id = state["items"]
        statuses = state["status"]
        kinds = desk_cfg["kinds"]

        candidates = [
            items_by_id[iid] for iid, s in statuses.items()
            if s == "queued" and iid in items_by_id
            and str(items_by_id[iid].get("kind") or "") in kinds
            and (account is None or items_by_id[iid].get("account") == account)
            and not _human_has_spoken(iid, state)
        ]
        # Same deterministic order the auto-approve pass uses, so the per-sweep
        # cap always bites the same items in the same order.
        candidates.sort(key=lambda i: (i.get("priority", 5),
                                       str(i.get("scheduled_at") or ""),
                                       str(i.get("id") or "")))
        tally["considered"] = len(candidates)

        ref_day = ts_now.strftime("%Y-%m-%d")
        posted_texts = _outbox.recent_posted_texts(state, ref_day)
        plan_charts = _load_plan_charts(root)
        cap = desk_cfg["max_approvals_per_sweep"]

        for it in candidates:
            iid = str(it.get("id") or "")
            try:
                verdict = audit_item(
                    it, now=ts_now, posted_texts=posted_texts,
                    plan_charts=plan_charts, media_enabled=media_enabled,
                    desk_cfg=desk_cfg,
                )
            except Exception as exc:  # noqa: BLE001
                # An audit that crashed proved nothing. The conservative verdict
                # is the only safe one: leave it queued for a human.
                log.warning("approval_desk: audit failed for %s (%s) — holding",
                            iid, exc)
                tally["held"] += 1
                tally["held_ids"].append(iid)
                tally["by_check"]["audit_error"] = (
                    tally["by_check"].get("audit_error", 0) + 1)
                continue

            if verdict.action == "quarantine":
                note = f"approval-desk: {verdict.check}: {verdict.evidence}"
                log.warning("approval-desk QUARANTINE %s (%s/%s): %s", iid,
                            it.get("account"), it.get("kind"), note)
                if live:
                    _outbox.transition(iid, "quarantined", actor="approval-desk",
                                       root=root, note=note[:500], now=ts_now,
                                       _state=state)
                tally["quarantined"] += 1
                tally["quarantined_ids"].append(iid)
                tally["by_check"][verdict.check] = (
                    tally["by_check"].get(verdict.check, 0) + 1)
                continue

            if verdict.action == "hold":
                log.info("approval-desk HOLD %s (%s/%s): %s — %s", iid,
                         it.get("account"), it.get("kind"), verdict.check,
                         verdict.evidence)
                tally["held"] += 1
                tally["held_ids"].append(iid)
                tally["by_check"][verdict.check] = (
                    tally["by_check"].get(verdict.check, 0) + 1)
                continue

            # APPROVE — subject to the per-sweep trickle valve. The cap counts
            # APPROVALS only: a quarantine is not a post going out and refusing
            # to record one past the cap would just leave a bad item queued to
            # be re-audited forever. An item over the cap stays `queued`
            # untouched and is re-audited next sweep against fresher evidence.
            if cap and tally["approved"] >= cap:
                tally["capped"] += 1
                tally["capped_ids"].append(iid)
                continue

            note = "approval-desk: " + ", ".join(verdict.passed)
            if live:
                if not _outbox.transition(iid, "approved", actor="approval-desk",
                                          root=root, note=note[:500], now=ts_now,
                                          _state=state):
                    log.warning("approval-desk %s: transition failed — leaving "
                                "queued", iid)
                    tally["held"] += 1
                    tally["held_ids"].append(iid)
                    continue
                log.info("approval-desk APPROVED %s (%s/%s)", iid,
                         it.get("account"), it.get("kind"))
            else:
                log.info("approval-desk WOULD APPROVE %s (%s/%s)", iid,
                         it.get("account"), it.get("kind"))
            tally["approved"] += 1
            tally["approved_ids"].append(iid)

    except Exception as exc:  # noqa: BLE001
        # A desk that cannot run degrades to the pre-desk world: nothing gets
        # approved, nothing gets destroyed, and the sweep continues.
        log.warning("approval_desk.run failed: %s", exc)
        tally["status"] = "error"
        tally["reason"] = str(exc)[:200]
    return tally
