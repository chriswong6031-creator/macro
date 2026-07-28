"""engine/marketing/desk_feed.py — per-account desk feeds (XG-W3, charter §4).

"Every account knows its day." Each live account's feed assembles candidates
from four lanes and hands them to the EXISTING generation paths:

  scheduled     franchise slots on the cadence resolver's clock
                (engine/marketing/franchises.py)
  breaking      press_lane candidates filtered by beat fit + the one-owner lock
                (engine/marketing/breaking_relevance.py, story_lock.py)
  market_hours  session posts from the live tape — movers, stamps, divergences
                (engine/marketing/movers_source.py, market_facts.py)
  analysis      nightly studio items — daily-read derivatives, chart-backed
                reactions, explainers (engine/marketing/content_studio.py)

THIS IS ASSEMBLY, NOT A NEW POSTING RAIL.  Nothing here posts. Nothing here
generates copy. The feed decides WHAT each desk considers; `content_studio` /
`copywriter` still write it, `outbox.enqueue` still queues it, the sentinel and
the approve-ladder still gate it. Every lane consumes an API that already
exists — this module adds no scraper, no provider, no queue.

RANKING IS DISPLAY-TIER INTERNAL.  The score is a deterministic, greppable sum
of named components; an LLM never scores (charter §2 amendment 9). The gauntlet
is a PROMOTION gate, not a build gate, so this ranking ships freely — but it may
never be called calibrated, and no component weight is load-bearing until XG-W6
telemetry ranks it. `_components` stays inspectable for exactly that reason
(charter §8: author-tier scorer weights are hypotheses).

CHRONICLE SEAM.  Context packs come from `engine.chronicle.context_pack.pack()`
— the W0 API, consumed directly and deliberately. Chronicle W1 (narratives) and
W2 (the injection helper) are UNBUILT; `pack()` returns `narratives: []` at W0 by
contract. When Chronicle-W2 lands its injection helper, `_chronicle_context()`
below is the single seam to reroute — it is the only call site in this module.

Public API:
    assemble(account, *, now, ...)   -> DeskFeed
    Candidate / DeskFeed / LANES
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

__all__ = ["LANES", "Candidate", "DeskFeed", "assemble"]

#: The four lanes of charter §4, in declaration order.
LANES: tuple[str, ...] = ("scheduled", "breaking", "market_hours", "analysis")

# ─────────────────────────────────────────────────────────────────────────────
# Ranking components. Each is a named, bounded contribution — never a learned
# weight, never an LLM judgment. Charter §8: these are HYPOTHESES; the
# `_components` dict on every candidate keeps them re-weightable.
# ─────────────────────────────────────────────────────────────────────────────
_LANE_BASE: dict[str, float] = {
    # Breaking outranks a scheduled slot: a franchise window is open all
    # session, a print is not (§7.5 why-now).
    "breaking": 40.0,
    "scheduled": 30.0,
    "market_hours": 25.0,
    "analysis": 20.0,
}
#: Content hierarchy (constitution §8.4): proprietary intelligence and
#: proprietary interpretation outrank commodity reaction.
_KIND_BONUS: dict[str, float] = {
    "signal": 10.0,
    "chart": 8.0,
    "receipt": 8.0,
    "theme_list": 6.0,
    "macro": 5.0,
    "mover": 4.0,
    "watchlist": 3.0,
    "event": 3.0,
    "education": 2.0,
}
#: A franchise slot is a recurring promise to the reader — §8.5's last-nine-post
#: diagnostic wants at least two items from a recognisable franchise.
_FRANCHISE_BONUS: float = 6.0
#: Fatigue penalty — an over-used n-gram is the anti-sameness tell.
_FATIGUE_PENALTY: float = 8.0
# NOTE: there is deliberately no Bridge bonus here. Bridge is evaluated by the
# value gate at EMISSION (after copy exists); at ASSEMBLY time there is no text
# to detect it in, so a bonus would be a constant nobody could earn. Charter §4
# does say Bridge presence "marks virality-option items for prime slots" — that
# belongs to the slotting step once a verdict exists, not to candidate ranking.


@dataclass(frozen=True)
class Candidate:
    """One thing this desk could post right now, with its context attached."""

    account: str
    lane: str
    kind: str
    #: Stable identity for dedup/telemetry across a run.
    key: str
    #: Short human-readable summary of what this candidate IS.
    title: str
    score: float
    #: Everything the generation call needs: context packs, persona memory,
    #: franchise contract, tape facts, source record.
    context: dict[str, Any] = field(default_factory=dict)
    #: Set for scheduled-lane candidates.
    franchise_id: str = ""
    #: Inspectable score breakdown (charter §8 — no weight is load-bearing).
    components: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "lane": self.lane,
            "kind": self.kind,
            "key": self.key,
            "title": self.title,
            "score": round(self.score, 3),
            "franchise": self.franchise_id,
            "components": dict(self.components),
            "context": dict(self.context),
        }


@dataclass(frozen=True)
class DeskFeed:
    """A ranked per-account feed plus the silences it chose."""

    account: str
    as_of: str
    candidates: tuple[Candidate, ...] = ()
    #: `franchises.Abstention` records — every empty slot, with its reason.
    abstentions: tuple[Any, ...] = ()
    #: Non-fatal notes (a lane that could not load its source).
    notes: tuple[str, ...] = ()

    def by_lane(self, lane: str) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if c.lane == lane)

    @property
    def lanes_present(self) -> set[str]:
        return {c.lane for c in self.candidates}

    def as_dict(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "as_of": self.as_of,
            "candidates": [c.as_dict() for c in self.candidates],
            "abstentions": [
                a.as_dict() if hasattr(a, "as_dict") else dict(a) for a in self.abstentions
            ],
            "notes": list(self.notes),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Context assembly
# ─────────────────────────────────────────────────────────────────────────────
def _chronicle_context(
    spec: dict, *, as_of: str, root: Path | str | None, token_budget: int = 1200
) -> dict[str, Any]:
    """THE CHRONICLE SEAM.

    Consumes the Chronicle W0 `pack()` API directly, as charted. Chronicle W1
    (LLM narratives) and W2 (the context-injection helper) are UNBUILT and this
    wave does not build them — `pack()` returns `narratives: []` at W0 by its
    own contract, which is the honest empty, not a failure.

    When Chronicle-W2 ships its injection helper, THIS FUNCTION is the only call
    site to reroute in this module. Keep it that way.
    """
    horizons = tuple((spec.get("context_packs") or {}).get("chronicle") or ("short",))
    try:
        from engine.chronicle.context_pack import pack

        return pack(horizons=horizons, as_of=as_of, token_budget=token_budget, root=root)
    except Exception:
        # A missing chronicle store degrades the feed's context, never the feed.
        return {"lines": [], "narratives": [], "coverage": {}, "budget_used": 0}


def _persona_context(
    account: str, *, now: datetime, root: Path | str | None
) -> dict[str, Any]:
    """Persona memory: recent posts, open promises, phrase fatigue.

    Charter §4: "Every generation call receives ... persona memory (opinion
    ledger, open promises, recent posts, phrase-fatigue counters)".

    RELATIONS ARE DELIBERATELY NOT CARRIED (review F19). The store holds public
    interaction context per author HANDLE; this context dict is what gets handed
    to a generation call, so putting handles in it creates a path by which a
    real person's interaction history could reach a prompt and from there a
    public post. The feed needs to know only whether relationships exist and at
    what stage, so it carries STAGE COUNTS — an aggregate with no handle in it.
    Callers that genuinely need the per-handle record (the XG-W4 reply desk)
    read `persona_memory.relations()` directly, where the access is visible.
    """
    empty = {
        "recent_posts": [],
        "open_promises": [],
        "phrase_fatigue": {},
        "relation_stage_counts": {},
    }
    try:
        from engine.marketing import persona_memory as pm

        rel = pm.relations(account, root=root)
        counts: dict[str, int] = {}
        for record in rel.values():
            stage = str(record.get("stage") or "") or "unknown"
            counts[stage] = counts.get(stage, 0) + 1
        return {
            "recent_posts": pm.recent_posts(account, now=now, root=root),
            "open_promises": pm.open_promises(account, now=now, root=root),
            "phrase_fatigue": pm.ngram_fatigue(account, now=now, root=root),
            "relation_stage_counts": counts,
        }
    except Exception:
        return dict(empty)


def _codex_context(spec: dict) -> dict[str, Any]:
    """The codex layers the copywriter voice pass needs (XG-W3 item 5)."""
    return {
        "worldview": spec.get("worldview") or "",
        "restraint": spec.get("restraint") or "",
        "beat": spec.get("beat") or "",
        "archetype": spec.get("archetype") or "",
        "register": ((spec.get("voice_codex") or {}).get("register") or ""),
        "franchises": list(spec.get("franchises") or []),
    }


def _load_spec(account: str, *, root: Path | str | None) -> dict:
    """The account's persona spec as a plain dict.

    `personas.load_all()` returns `dict[str, PersonaSpec]` — a MAPPING keyed by
    id, whose values are dataclasses, not raw dicts. Getting that wrong is
    silent: iterating the mapping yields id STRINGS, every attribute lookup
    misses, and the caller degrades to an empty spec — which reads as "this
    account declares no session" and quietly disables the territory clock.
    """
    try:
        from engine.marketing.personas import load_all

        specs = load_all(root) if root is not None else load_all()
        spec = specs.get(str(account))
        if spec is None:
            return {}
        return spec.as_dict()
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Lanes
# ─────────────────────────────────────────────────────────────────────────────
def _weights(cfg: dict | None) -> dict[str, Any]:
    """Resolve the ranking knobs from config, fail-soft to the declared defaults.

    Charter §8: these are hypotheses held as config, never constants. A missing
    or malformed block degrades to the defaults rather than blanking a feed.
    """
    block = (cfg or {}).get("desk_feed") or {}
    lanes = dict(_LANE_BASE)
    for k, v in (block.get("lane_weights") or {}).items():
        try:
            lanes[str(k)] = float(v)
        except (TypeError, ValueError):
            continue

    def _num(key: str, default: float) -> float:
        try:
            return float(block[key])
        except (KeyError, TypeError, ValueError):
            return default

    return {
        "lanes": lanes,
        "franchise_bonus": _num("franchise_bonus", _FRANCHISE_BONUS),
        "fatigue_penalty": _num("fatigue_penalty", _FATIGUE_PENALTY),
        "token_budget": int(_num("chronicle_token_budget", 1200)),
    }


def _lane_scheduled(
    account: str,
    *,
    now: datetime,
    spec: dict,
    root: Path | str | None,
    cfg: dict | None,
    weights: dict[str, Any],
    franchise_history: Sequence[tuple[datetime, str]],
    base_context: dict[str, Any],
) -> tuple[list[Candidate], list[Any]]:
    """Franchise slots that are OPEN right now. Windows, not quotas."""
    from engine.marketing import franchises as fr

    cands: list[Candidate] = []
    abstentions: list[Any] = []

    # Every DISABLED franchise for this account is an explicit, logged silence —
    # a parked franchise that vanished silently would be indistinguishable from
    # one nobody ever wrote.
    for f in fr.for_account(account, root=root):
        if not fr.is_enabled(f, cfg):
            abstentions.append(
                fr.abstain(
                    None,
                    "franchise_disabled",
                    now=now,
                    account=account,
                    franchise_id=f.id,
                    detail={"note": f.note or "disabled by config"},
                )
            )

    for slot in fr.open_slots(
        account, now=now, history=franchise_history, root=root, cfg=cfg
    ):
        f = slot.franchise
        ctx = dict(base_context)
        ctx.update(
            {
                "franchise": {
                    "id": f.id,
                    "display_name": f.display_name,
                    "contract": list(f.contract),
                    "classification": f.classification,
                    # Load-bearing: a name that trips the house vocab guard must
                    # never be handed to a drafter as verbatim copy.
                    "copy_safe_name": f.copy_safe_name,
                    "requires_measured_input": f.requires_measured_input,
                },
                "slot": {
                    "day": slot.day,
                    "opens_at": slot.opens_at.isoformat(),
                    "closes_at": slot.closes_at.isoformat(),
                },
            }
        )
        comp = {
            "lane_base": weights["lanes"].get("scheduled", _LANE_BASE["scheduled"]),
            "kind": _KIND_BONUS.get(f.kind, 0.0),
            "franchise": weights["franchise_bonus"],
        }
        cands.append(
            Candidate(
                account=account,
                lane="scheduled",
                kind=f.kind,
                key=f"scheduled:{f.id}:{slot.day}",
                title=f.display_name,
                score=sum(comp.values()),
                context=ctx,
                franchise_id=f.id,
                components=comp,
            )
        )
    return cands, abstentions


def _lane_breaking(
    account: str,
    *,
    now: datetime,
    spec: dict,
    root: Path | str | None,
    weights: dict[str, Any],
    breaking_items: Sequence[dict],
    outbox_items: Sequence[dict],
    cfg: dict,
    base_context: dict[str, Any],
) -> tuple[list[Candidate], list[Any]]:
    """press_lane candidates filtered by beat fit + the one-owner story lock."""
    from engine.marketing import franchises as fr

    cands: list[Candidate] = []
    abstentions: list[Any] = []
    if not breaking_items:
        return cands, abstentions

    try:
        from engine.marketing import story_lock as sl
    except Exception:
        sl = None  # type: ignore[assignment]

    # Beat fit: which wire classes belong to this desk. wire_routing is the
    # XG-W2 authority on that mapping — consumed, never re-derived here.
    routed_classes: set[str] = set()
    try:
        routing = (cfg or {}).get("wire_routing") or {}
        for cls, owner in (routing.get("classes") or {}).items():
            if owner == account:
                routed_classes.add(str(cls))
        if routing.get("default") == account:
            routed_classes.add("none")
    except Exception:
        pass

    # FAIL CLOSED ON MISSING ROUTING (review F2). An account with NO routed
    # classes owns no wire beat — the correct output is silence, not the
    # unfiltered firehose. The first cut read `if routed_classes and cls not in
    # routed_classes`, so an account absent from `wire_routing` skipped the
    # filter entirely and every breaking item became one of its candidates. That
    # is the exact inversion of charter §2 amendment 6: the accounts most likely
    # to be missing from routing are the ones that should be quietest.
    if not routed_classes:
        abstentions.append(
            fr.abstain(
                None,
                "no_wire_routing",
                now=now,
                account=account,
                detail={
                    "candidates_withheld": len(breaking_items),
                    "note": "account owns no wire_routing class; add one in config/marketing.yml",
                },
            )
        )
        return cands, abstentions

    for item in breaking_items:
        cls = str(item.get("event_class") or "none")
        if cls not in routed_classes:
            abstentions.append(
                fr.abstain(
                    None,
                    "weak_persona_fit",
                    now=now,
                    account=account,
                    detail={"event_class": cls, "headline": str(item.get("headline"))[:120]},
                )
            )
            continue

        # ONE CONVERSATION, ONE OWNER (charter §2 amendment 6) — a hard lock.
        #
        # FAIL CLOSED (review F3). A lock you cannot consult is a lock that
        # FAILED. The first cut swallowed the exception and fell through to
        # emitting the candidate, which turns "hard lock" into "hard lock unless
        # it throws" — and the throw is most likely exactly when the outbox is
        # mid-write, i.e. when another desk is claiming this very story.
        key = ""
        if sl is not None:
            try:
                key = sl.story_key(
                    cluster_key=item.get("cluster_key"),
                    event_id=item.get("id"),
                    headline=item.get("headline"),
                )
                verdict = sl.check(account, key, outbox_items, now=now, cfg=cfg)
                allowed = verdict.allowed
                owner = verdict.owner
            except Exception as exc:
                abstentions.append(
                    fr.abstain(
                        None,
                        "cross_account_collision_check_failed",
                        now=now,
                        account=account,
                        detail={
                            "headline": str(item.get("headline"))[:120],
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                )
                continue
            if not allowed:
                abstentions.append(
                    fr.abstain(
                        None,
                        "cross_account_collision",
                        now=now,
                        account=account,
                        detail={"story_key": key, "owner": owner},
                    )
                )
                continue

        salience = float(item.get("salience") or 0.0)
        comp = {
            "lane_base": weights["lanes"].get("breaking", _LANE_BASE["breaking"]),
            "kind": _KIND_BONUS.get("event", 0.0),
            # Salience is 0-100 from breaking_relevance; scaled to a bounded
            # contribution so one loud headline cannot dominate the whole feed.
            "salience": round(salience / 5.0, 3),
        }
        ctx = dict(base_context)
        ctx.update(
            {
                "breaking": {
                    "headline": item.get("headline"),
                    "url": item.get("url"),
                    "source": item.get("source_name") or item.get("source"),
                    "source_tier": item.get("source_tier"),
                    "published_at": item.get("published_at"),
                    "event_class": cls,
                    "salience": salience,
                    "matched": item.get("matched") or {},
                },
                "story_key": key,
            }
        )
        cands.append(
            Candidate(
                account=account,
                lane="breaking",
                kind="event",
                key=f"breaking:{item.get('id') or key}",
                title=str(item.get("headline") or "")[:120],
                score=sum(comp.values()),
                context=ctx,
                components=comp,
            )
        )
    return cands, abstentions


def _lane_market_hours(
    account: str,
    *,
    now: datetime,
    spec: dict,
    root: Path | str | None,
    weights: dict[str, Any],
    cfg: dict | None,
    movers: Sequence[dict],
    mover_allowlist: str,
    base_context: dict[str, Any],
) -> tuple[list[Candidate], list[Any]]:
    """Live-tape session posts, inside the account's own session.

    ALLOWLIST-AWARE: the movers handed in are expected to come from
    `movers_source.top_movers(..., tier_map=...)`, which already drops T3
    cashtags. We do not re-derive that filter; we record that it applied.
    """
    from engine.marketing import franchises as fr
    from engine.marketing import cadence_resolver as cr

    cands: list[Candidate] = []
    abstentions: list[Any] = []

    # PER-CALL LANE ALLOWLIST (review F5). This lane builds a mover item from the
    # live tape without consulting tilt — structurally the same thing
    # `publish.publish_time_movers` does, so it is bound by the SAME allowlist
    # rather than a second one invented here. config/marketing.yml says of that
    # list: "UNLOCK: charter §6 XG-W2 + XG-W3. Widen this list then, not before."
    # XG-W3 is the named unlock, but widening it is an ARMING decision for the
    # operator — this wave reads the list, it does not edit it.
    allow = (
        ((cfg or {}).get("publish") or {}).get("publish_time_movers") or {}
    ).get("accounts")
    allow = [str(a) for a in allow] if allow is not None else ["flagship", "founder"]
    if account not in allow:
        abstentions.append(
            fr.abstain(
                None,
                "no_market_hours_lane",
                now=now,
                account=account,
                detail={"allowlist": allow, "candidates_withheld": len(movers)},
            )
        )
        return cands, abstentions

    if not movers:
        return cands, abstentions

    # An account outside its declared session does not run a market-hours lane —
    # that is the whole point of a territory clock (Cici files Asia, not the US
    # afternoon). No session declared = always in session (resolver semantics).
    try:
        profile = cr.profile_from_cadence(account, spec.get("cadence") or {}, source="spec")
        if profile is not None and profile.has_session and not cr.in_session(profile, now):
            abstentions.append(
                fr.abstain(
                    None,
                    "outside_window",
                    now=now,
                    account=account,
                    detail={"lane": "market_hours", "tz": profile.tz},
                )
            )
            return cands, abstentions
    except Exception:
        pass

    for m in movers:
        ticker = str(m.get("ticker") or "")
        if not ticker:
            continue
        comp = {
            "lane_base": weights["lanes"].get("market_hours", _LANE_BASE["market_hours"]),
            "kind": _KIND_BONUS.get("mover", 0.0),
            "move": round(min(abs(float(m.get("pct") or m.get("change_pct") or 0.0)), 20.0) / 2.0, 3),
        }
        ctx = dict(base_context)
        # NO UNCONDITIONAL PROVENANCE STAMP (review F5). The first cut wrote
        # `"allowlist": "cashtag_tiers"` on every candidate regardless of whether
        # any tier filtering had happened — a claim about the caller's inputs
        # that this module cannot verify, and exactly the kind of decorative
        # provenance that reads as a guarantee downstream. The caller states what
        # it applied, or nothing is stated.
        ctx.update({"mover": dict(m)})
        if mover_allowlist:
            ctx["mover_allowlist"] = str(mover_allowlist)
        cands.append(
            Candidate(
                account=account,
                lane="market_hours",
                kind="mover",
                key=f"market_hours:{ticker}",
                title=f"{ticker} on the tape",
                score=sum(comp.values()),
                context=ctx,
                components=comp,
            )
        )
    return cands, abstentions


def _lane_analysis(
    account: str,
    *,
    now: datetime,
    root: Path | str | None,
    weights: dict[str, Any],
    studio_items: Sequence[dict],
    base_context: dict[str, Any],
) -> tuple[list[Candidate], list[Any]]:
    """Nightly studio items — the existing content plan, as candidates."""
    cands: list[Candidate] = []
    for it in studio_items:
        kind = str(it.get("type") or it.get("kind") or "macro")
        comp = {
            "lane_base": weights["lanes"].get("analysis", _LANE_BASE["analysis"]),
            "kind": _KIND_BONUS.get(kind, 0.0),
        }
        ctx = dict(base_context)
        ctx.update({"studio_item": dict(it)})
        cands.append(
            Candidate(
                account=account,
                lane="analysis",
                kind=kind,
                key=f"analysis:{it.get('id') or it.get('slot') or it.get('headline')}",
                title=str(it.get("headline") or "")[:120],
                score=sum(comp.values()),
                context=ctx,
                components=comp,
            )
        )
    return cands, []


# ─────────────────────────────────────────────────────────────────────────────
# Assembly
# ─────────────────────────────────────────────────────────────────────────────
def assemble(
    account: str,
    *,
    now: datetime,
    cfg: dict | None = None,
    root: Path | str | None = None,
    breaking_items: Sequence[dict] = (),
    movers: Sequence[dict] = (),
    studio_items: Sequence[dict] = (),
    outbox_items: Sequence[dict] = (),
    franchise_history: Sequence[tuple[datetime, str]] = (),
    #: What the CALLER filtered `movers` by, if anything (e.g. "cashtag_tiers").
    #: Recorded verbatim; this module never asserts a filter it did not apply.
    mover_allowlist: str = "",
    spec: dict | None = None,
    token_budget: int = 1200,
) -> DeskFeed:
    """Assemble `account`'s desk feed at `now`.

    Every input is INJECTED rather than fetched here: the caller owns the
    outbox read, the press poll and the movers load, so this module does no I/O
    beyond the persona spec, persona memory and the chronicle pack. That keeps
    the feed unit-testable on a fixture clock with zero network and zero
    fixture files, and it keeps one poller per source (the house quota law).

    `franchise_history` is [(emitted_at, franchise_id), ...] for this account.
    """
    cfg = cfg or {}
    spec = spec if spec is not None else _load_spec(account, root=root)
    as_of = now.strftime("%Y-%m-%d")
    weights = _weights(cfg)

    # Franchise history drives the per-day / per-week ceilings. When the caller
    # does not supply it explicitly, derive it from the outbox items it already
    # handed us — the franchise id round-trips through
    # `item["source"]["franchise"]`. Without this the scheduler would see every
    # daily slot as permanently unspent and "windows, not quotas" would quietly
    # become "unlimited".
    if not franchise_history and outbox_items:
        try:
            from engine.marketing import franchises as _fr

            franchise_history = _fr.history_from_items(outbox_items, account=account)
        except Exception:
            franchise_history = ()
    if token_budget == 1200:
        # An explicit argument still wins; otherwise config decides.
        token_budget = weights["token_budget"]

    base_context: dict[str, Any] = {
        "account": account,
        "as_of": as_of,
        "now": now.isoformat(),
        "codex": _codex_context(spec),
        "persona_memory": _persona_context(account, now=now, root=root),
        "chronicle": _chronicle_context(spec, as_of=as_of, root=root, token_budget=token_budget),
    }

    cands: list[Candidate] = []
    abstentions: list[Any] = []
    notes: list[str] = []

    for fn, kwargs in (
        (
            _lane_scheduled,
            dict(
                spec=spec,
                root=root,
                cfg=cfg,
                weights=weights,
                franchise_history=franchise_history,
                base_context=base_context,
            ),
        ),
        (
            _lane_breaking,
            dict(
                spec=spec,
                root=root,
                weights=weights,
                breaking_items=breaking_items,
                outbox_items=outbox_items,
                cfg=cfg,
                base_context=base_context,
            ),
        ),
        (
            _lane_market_hours,
            dict(spec=spec, root=root, cfg=cfg, weights=weights, movers=movers,
                 mover_allowlist=mover_allowlist, base_context=base_context),
        ),
        (
            _lane_analysis,
            dict(root=root, weights=weights, studio_items=studio_items, base_context=base_context),
        ),
    ):
        try:
            c, a = fn(account, now=now, **kwargs)  # type: ignore[operator]
            cands.extend(c)
            abstentions.extend(a)
        except Exception as exc:  # one broken lane must not blank the feed
            notes.append(f"{fn.__name__}: {type(exc).__name__}: {exc}")

    # ── fatigue penalty ─────────────────────────────────────────────────────
    # TODO(xg-w3-review): F17 — this penalty is VACUOUS for two of the four
    # lanes. It matches worn-out n-grams against `candidate.title`, but a
    # scheduled candidate's title is the franchise DISPLAY NAME ("Before New
    # York Wakes") and a market-hours title is "<TICKER> on the tape" — neither
    # is generated prose, so neither can ever contain a fatigued phrase. It bites
    # only on breaking/analysis titles, which are real headlines. Fixing it means
    # scoring the candidate's CONTEXT (the facts it would be written from) rather
    # than its label, which needs a defensible notion of "the text this candidate
    # would become" — deferred, not silently left to look like it works.
    fatigue = (base_context["persona_memory"] or {}).get("phrase_fatigue") or {}
    if fatigue:
        penalised: list[Candidate] = []
        for c in cands:
            title_l = str(c.title).lower()
            if any(g in title_l for g in fatigue):
                comp = dict(c.components)
                comp["fatigue"] = -weights["fatigue_penalty"]
                penalised.append(
                    Candidate(
                        account=c.account,
                        lane=c.lane,
                        kind=c.kind,
                        key=c.key,
                        title=c.title,
                        score=sum(comp.values()),
                        context=c.context,
                        franchise_id=c.franchise_id,
                        components=comp,
                    )
                )
            else:
                penalised.append(c)
        cands = penalised

    # Deterministic order: score desc, then lane order, then key — never a set
    # iteration or a dict order, so two runs on one clock rank identically.
    cands.sort(key=lambda c: (-c.score, LANES.index(c.lane) if c.lane in LANES else 9, c.key))

    return DeskFeed(
        account=account,
        as_of=as_of,
        candidates=tuple(cands),
        abstentions=tuple(abstentions),
        notes=tuple(notes),
    )
