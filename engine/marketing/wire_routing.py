"""engine.marketing.wire_routing — which account owns a wire emission (XG-W2).

THE GAP THIS CLOSES. ``engine/marketing/press_lane.py`` hardcoded
``_ACCOUNT = "flagship"`` at module scope, so the entire press/wire lane could
address exactly one of the seven live Buffer channels. That was invisible in
config: an operator reading ``publish.channels`` saw seven addressable accounts
and no hint that the wire lane could only ever speak as one of them. Worse, the
account whose whole job IS the wire — ``mastermind_news`` — could not receive a
wire item even after being enabled, because the routing lived in a Python
constant.

Routing is now CONFIG (``config/marketing.yml`` ``wire_routing:``):

    wire_routing:
      default: flagship
      classes:
        macro_print: flagship
        policy: flagship
        ...

A routing change is a config edit, never a code edit. The mapping keys are
``breaking_relevance`` event_class slugs (the same slugs ``press_lane``'s
``_CLASS_LABELS`` table renders).

LIVENESS IS NOT ROUTING. The map may name an account that is not armed yet —
``mastermind_news`` is wired-but-dark on purpose. Routing therefore resolves
through the accounts model (``engine.marketing.accounts.effective_accounts``):
a class routed to a disabled account falls back to the default with a
start-of-line ``::warning``, so the operator sees the intent AND the fact that
it is not in force. Enabling the desk is what arms the route — exactly one flip,
in ``desk_network``, where every other arming decision already lives.

SPILL IS ROUTING TOO (W4d). When the account a class routes to has spent its
daily wire budget, the surplus may move to ANOTHER wire desk rather than being
dropped — but only to a desk the operator has already declared a wire owner.
``spill_pool`` answers that question from the SAME config and the SAME liveness
read as ``route``, so there is exactly one answer to "may this desk carry a wire
relay". It deliberately does NOT return every enabled account in
``desk_network``: the persona desks (meagan/sophia/kelly/cici/founder) are
authored voices, and the charter is explicit that wire accounts RELAY and never
take a stance (masterplan §4 safety rails). Handing a persona a raw press relay
would be a voice violation dressed up as a volume fix.

A DARK DESK PARKS, IT DOES NOT DONATE ITS VOLUME (W5, 2026-08-03). The
fallback described above — "a class routed to a disabled account falls back to
the default" — was written for a lane that emitted a handful of items a day. It
is the wrong shape for a FIREHOSE: the wire desk's whole traffic silently became
the brand account's traffic the moment an operator flipped one switch, and the
operator saw the result as four posts from one Fed appearance inside an hour on
@mastermindx001. Redirecting is now OPT-IN (``wire_routing.dark_desk.policy``,
default ``park``); the default is that the item stays addressed to the desk that
OWNS it, is COUNTED in :func:`park_census`, is announced once per desk with a
start-of-line ``::warning``, and parks at dispatch (the publisher quarantines an
item addressed to a desk that is not enabled, reason ``account_disabled``) —
where the admin can see it. A brand desk never inherits a dark desk's volume by
default. The narrow escape hatch is ``dark_desk.severity_exception``, OFF by
default and bounded by an explicit severity floor: one genuinely huge single
event may still be mirrored onto a live desk. Volume never may.

VOLUME IS ITS OWN BOUND, INDEPENDENT OF ROUTING (W5). Routing answers "whose
item is this"; it cannot answer "how many of these may one desk take". Those are
different questions and the lane had only the first, plus a press-lane-local
daily counter that lives in daemon state — so a lost or reset cursors.json, and
every OTHER lane that emits ``kind="breaking"`` (hot_tape, fastlane, the
earnings call lane), were entirely outside it. Measured on the committed outbox
for 2026-08-03: **11** ``kind="breaking"`` items on ``flagship`` in one day,
every one of them ``event_class=macro_print`` — i.e. correctly routed, never
redirected, and still a print ticker on the brand account. ``wire_volume.breaking``
is the bound that closes that: a rolling-window ceiling on how many breaking
items one ACCOUNT may take, read from the outbox itself (the record of what the
network actually produced) rather than from any one lane's private counter. It
binds here, in the routing seam every wire lane already goes through, so surplus
moves to a declared wire desk with headroom instead of piling on the brand.

Public API:
    route(event_class, *, cfg, root=None)  -> str          (the account id)
    routing_table(cfg, *, root=None)       -> dict         (class -> account, resolved)
    default_account(cfg)                   -> str
    spill_pool(cfg, *, root=None)          -> list[str]    (live wire desks WITH headroom)
    resolve_desk(candidate, *, cfg, ...)   -> DeskVerdict  (liveness + park policy)
    breaking_cap_verdict(account, *, cfg)  -> CapVerdict   (rolling per-account volume)
    park_census()                          -> dict         (parks counted this process)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: The account every wire item went to before XG-W2, and the fallback when
#: config declares nothing. Keeping the historical value as the fallback means a
#: config-less checkout behaves exactly as it did before this module existed.
DEFAULT_ACCOUNT = "flagship"


def _block(cfg: dict | None) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        return {}
    raw = cfg.get("wire_routing")
    return raw if isinstance(raw, dict) else {}


def default_account(cfg: dict | None) -> str:
    """``wire_routing.default``, or the historical flagship fallback."""
    value = str(_block(cfg).get("default") or "").strip()
    return value or DEFAULT_ACCOUNT


def _enabled_accounts(cfg: dict | None, root: Path | str | None) -> set[str] | None:
    """Ids of accounts the accounts model considers live, or None when liveness
    is UNKNOWN (the accounts model could not be consulted).

    None and the empty set are different answers and callers must not conflate
    them — the first version of this function returned an empty set for both,
    and the callers' ``if live and …`` test then treated "unknown" as "no
    constraint" and let a configured DARK account through. That is a silent
    widening in the one failure mode where widening is least defensible, and it
    is the exact opposite of what this module promises. Unknown liveness now
    routes to the default, which is the pre-XG-W2 behaviour and always safe.
    """
    try:
        from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

        return {
            str(a.get("id") or "")
            for a in effective_accounts(cfg, root)
            if a.get("enabled")
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("wire_routing: accounts model unavailable (%s) — default only", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Dark-desk policy (W5) — PARK by default, redirect only when asked
# ─────────────────────────────────────────────────────────────────────────────

#: The default when config declares nothing. ``park`` is deliberately NOT the
#: historical behaviour: the historical behaviour is the defect. A wire desk
#: carries firehose volume by construction, and "silently becomes another
#: account's traffic" is never a safe default for a firehose.
DEFAULT_DARK_DESK_POLICY = "park"

#: Severity floor for the narrow redirect exception when config enables it but
#: names no floor. 90 is deliberately high — this hatch exists for ONE
#: genuinely-huge single event, never for a busy tape.
DEFAULT_SEVERITY_EXCEPTION_FLOOR = 90.0

_POLICIES = ("park", "redirect")


def _dark_block(cfg: dict | None) -> dict[str, Any]:
    raw = _block(cfg).get("dark_desk")
    return raw if isinstance(raw, dict) else {}


def dark_desk_policy(cfg: dict | None) -> str:
    """``park`` (default) or ``redirect`` — what happens to a dark desk's item.

    An unrecognised value reads as ``park`` with an annotation rather than being
    coerced: a typo that silently resolves to ``redirect`` would re-open the
    exact hole this key was added to close, and it would do it invisibly.
    """
    raw = str(_dark_block(cfg).get("policy") or "").strip().lower()
    if not raw:
        return DEFAULT_DARK_DESK_POLICY
    if raw in _POLICIES:
        return raw
    _warn_once(
        ("bad-policy", raw),
        f"::warning title=wire-routing-policy-invalid::"
        f"wire_routing.dark_desk.policy={raw!r} is not one of {_POLICIES} — "
        f"reading it as {DEFAULT_DARK_DESK_POLICY!r}. A typo here must never "
        f"resolve to 'redirect' on its own.",
    )
    return DEFAULT_DARK_DESK_POLICY


def severity_exception(cfg: dict | None) -> dict[str, Any]:
    """The narrow high-severity redirect hatch, resolved. OFF unless configured.

    Shape: ``{"enabled": bool, "min_severity": float, "to": str}``. ``to`` empty
    means "the routing default", resolved by the caller against liveness — this
    function does no liveness read of its own, because a config accessor that
    quietly consults desk_network is how a routing table starts lying (the law
    this module opens with).
    """
    raw = _dark_block(cfg).get("severity_exception")
    blk = raw if isinstance(raw, dict) else {}
    enabled = bool(blk.get("enabled"))
    try:
        floor = float(blk.get("min_severity", DEFAULT_SEVERITY_EXCEPTION_FLOOR))
    except (TypeError, ValueError):
        floor = DEFAULT_SEVERITY_EXCEPTION_FLOOR
    return {"enabled": enabled, "min_severity": floor,
            "to": str(blk.get("to") or "").strip()}


@dataclass(frozen=True)
class DeskVerdict:
    """The answer to "may this desk take this item, and if not, what now?".

    ``account`` is ALWAYS the address to use. When ``parked`` is True that
    address is a desk the accounts model says is dark, and the caller is being
    told the item will not post: it exists so a lane that can refuse cheaply
    (before a raster and an LLM call) has something to test, while a lane that
    cannot still addresses the item to its rightful owner and lets the
    publisher's dispatch-time park record it as ``account_disabled``.
    """
    account: str
    parked: bool = False
    reason: str = ""
    detail: str = ""
    #: True only when the high-severity exception moved the item to another desk.
    redirected: bool = False


#: Parks counted in THIS process, {account: n}. "Counted, not silent" is the
#: house law the press lane's headroom census already follows: a silent
#: `continue` is not a decision, it is a leak. The radar and the press daemon
#: both report this in their pass summary.
_PARK_CENSUS: dict[str, int] = {}

#: Annotation keys already printed in THIS process. route() runs once per press
#: item and the daemon ticks on an interval, so an unarmed route would otherwise
#: print the same annotation thousands of times a day and bury the Actions
#: summary it exists to surface. Keyed by (kind, account), not by (class,
#: account): the operator's action is the same one desk_network flip whichever
#: class hit it.
_WARNED_DARK: set[Any] = set()


def park_census() -> dict[str, int]:
    """``{account: parked_items}`` for this process. A copy; never the live dict."""
    return dict(_PARK_CENSUS)


def reset_dark_route_warnings() -> None:
    """Clear the once-per-process warning set AND the park census (tests)."""
    _WARNED_DARK.clear()
    _PARK_CENSUS.clear()


def _warn_once(key: Any, line: str) -> None:
    """Print a start-of-line annotation at most once per key per process.

    BARE print, line-start, flushed (house law): every builder here logs with a
    prefixing format, so ``log.warning("::warning …")`` emits
    ``WARNING ::warning …`` and GitHub drops it silently — the call reviews as
    an alarm and produces nothing in the Actions summary.
    """
    if key in _WARNED_DARK:
        return
    _WARNED_DARK.add(key)
    print(line, flush=True)


def _subject(event_class: Any) -> str:
    """"event_class 'policy'" for the press wire, "this lane" for the tape.

    The tape passes no class (``severity_account`` routes by severity), and
    interpolating the account id into the class slot produced the nonsense
    "event_class 'mastermind_news' routes to 'mastermind_news'".
    """
    return f"event_class {event_class!r}" if event_class is not None else "this lane"


def _warn_dark_park(event_class: Any, acct: str, *, unknown: bool) -> None:
    """Announce that a dark desk's item is PARKED, not donated."""
    why = ("liveness could not be resolved" if unknown
           else "is not enabled in desk_network")
    _warn_once(
        ("park", acct),
        f"::warning title=wire-routing-parked::{_subject(event_class)} "
        f"routes to {acct!r}, which {why} — the item is PARKED on that desk, "
        f"not moved onto a live one (it will quarantine at dispatch with reason "
        f"account_disabled, where the admin can count it). A wire desk's volume "
        f"must never silently become a brand desk's volume: that is how one Fed "
        f"appearance became four posts on the flagship. Arm the desk in "
        f"desk_network, or set wire_routing.dark_desk.policy: redirect if you "
        f"genuinely want another desk to carry it.",
    )


def _warn_dark_redirect(event_class: Any, acct: str, fallback: str, *,
                        unknown: bool) -> None:
    """Announce the OPT-IN redirect (policy: redirect, or the severity hatch)."""
    why = ("liveness could not be resolved" if unknown
           else "is not enabled in desk_network")
    _warn_once(
        ("redirect", acct),
        f"::warning title=wire-routing-dark::{_subject(event_class)} routes "
        f"to {acct!r}, which {why} — falling back to {fallback!r}. Enable the "
        f"desk to arm the route.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-account wire VOLUME (W5) — a rolling ceiling on kind="breaking"
# ─────────────────────────────────────────────────────────────────────────────

#: In-code defaults, so a config-less checkout still has a bound. These are not
#: placeholders: they are the numbers measured against the 2026-08-02/03 tape.
#: The committed outbox put 11 breaking items on `flagship` in one day and the
#: operator's verdict on that volume was unambiguous, so the brand desk sits
#: BELOW the network default rather than at it.
DEFAULT_BREAKING_WINDOW_HOURS = 24
DEFAULT_BREAKING_PER_WINDOW = 8

#: The kinds this ceiling governs. It is deliberately ONE kind: the cap exists
#: because wire relays arrive in bursts of near-identical items, which is not
#: true of the nightly ladder's planned kinds.
_CAPPED_KIND = "breaking"


def _volume_block(cfg: dict | None) -> dict[str, Any]:
    if not isinstance(cfg, dict):
        return {}
    raw = cfg.get("wire_volume")
    if not isinstance(raw, dict):
        return {}
    blk = raw.get(_CAPPED_KIND)
    return blk if isinstance(blk, dict) else {}


def breaking_window_hours(cfg: dict | None) -> int:
    """``wire_volume.breaking.window_hours``, or the in-code default.

    ROLLING, not calendar-daily, and the difference is the whole point on this
    lane. A calendar day resets at midnight, so a tape that fires at 23:00 can
    spend a full day's budget and then spend another one an hour later — which
    is precisely the "four posts inside one hour" shape being fixed.
    """
    try:
        value = int(_volume_block(cfg).get("window_hours",
                                           DEFAULT_BREAKING_WINDOW_HOURS))
    except (TypeError, ValueError):
        return DEFAULT_BREAKING_WINDOW_HOURS
    return value if value > 0 else DEFAULT_BREAKING_WINDOW_HOURS


def breaking_cap_for(account: str, cfg: dict | None) -> int:
    """This account's breaking ceiling for one rolling window.

    Precedence: ``wire_volume.breaking.accounts.<id>`` → ``…default_per_window``
    → :data:`DEFAULT_BREAKING_PER_WINDOW`. A negative number means UNLIMITED and
    is the only way to switch the ceiling off for a desk — 0 is a real zero, so
    an operator who wants a desk to stop taking wire items can say so without
    the code second-guessing them.

    Junk is IGNORED with an annotation rather than coerced, for the reason
    ``press_lane._resolve_top_k`` states one file over: a mistyped cap that
    silently reads as 0 is a dark lane, and this stack has been dark for reasons
    exactly that dull before.
    """
    blk = _volume_block(cfg)
    accounts = blk.get("accounts")
    acct = str(account or "").strip()
    for raw, home in ((accounts.get(acct) if isinstance(accounts, dict) else None,
                       f"accounts.{acct}"),
                      (blk.get("default_per_window"), "default_per_window")):
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            _warn_once(
                ("cap-invalid", home, str(raw)),
                f"::warning title=wire-volume-cap-invalid::"
                f"wire_volume.breaking.{home}={raw!r} is not an integer — "
                f"ignoring it and falling through (default "
                f"{DEFAULT_BREAKING_PER_WINDOW}).",
            )
    return DEFAULT_BREAKING_PER_WINDOW


#: (mtime_ns, size) of the outbox files the last count was built from, plus that
#: count. press_lane calls route() once per candidate per tick and read_items_all
#: parses the whole queue, so an uncached read would turn a volume ceiling into a
#: throughput problem. Keyed on file IDENTITY rather than on a clock: an enqueue
#: appends synchronously, so any item booked earlier in the same tick changes the
#: stat and invalidates this — a TTL cache would have let a lane overshoot its own
#: ceiling inside one pass, which is the one failure a cap may not have.
_COUNT_CACHE: dict[Any, tuple[Any, dict[str, int]]] = {}


def reset_volume_cache() -> None:
    """Drop the memoised outbox counts (tests, and any caller that mutates it)."""
    _COUNT_CACHE.clear()


def _outbox_stamp(root: Path | str | None) -> Any:
    """A cheap identity for the outbox files, or None when it cannot be taken."""
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415

        stamp = []
        for path in (_ob._items_path(root), _ob._host_items_path(root)):
            try:
                st = Path(path).stat()
                stamp.append((st.st_mtime_ns, st.st_size))
            except OSError:
                stamp.append(None)
        return tuple(stamp)
    except Exception:  # noqa: BLE001 — no stamp just means no caching
        return None


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def breaking_counts(
    root: Path | str | None = None,
    *,
    window_hours: int = DEFAULT_BREAKING_WINDOW_HOURS,
    now: datetime | None = None,
) -> dict[str, int]:
    """``{account: kind="breaking" items produced inside the window}``.

    THE OUTBOX IS THE DENOMINATOR, not any one lane's counter. press_lane keeps
    ``wire_day_counts`` in daemon state; that counter is per-lane and per-host,
    it resets with a fresh checkout, and it cannot see the three OTHER lanes that
    emit ``kind="breaking"`` (hot_tape, fastlane, the earnings call lane). A
    ceiling built on it would bound one producer while the account it protects
    took the sum of four.

    PRODUCED, NOT POSTED — deliberate. An item that was rendered, phrased and
    enqueued has already spent a Chrome raster and an LLM call, and the operator
    complaint is about how much of this content the network MAKES for one desk.
    Counting only the ones that survived to X would let a lane over-produce
    without limit as long as the graves were downstream.

    Reads through ``outbox.read_items_all`` (tracked queue + the gitignored
    daemon spool), the same corpus the enqueue dedup guards use. [] on any error
    — a ceiling that cannot read its own evidence must not become a silent
    publication stopper.
    """
    stamp = _outbox_stamp(root)
    key = (str(root), int(window_hours))
    if stamp is not None:
        cached = _COUNT_CACHE.get(key)
        if cached is not None and cached[0] == stamp:
            return dict(cached[1])

    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    floor = ref - timedelta(hours=int(window_hours))

    counts: dict[str, int] = {}
    try:
        from engine.marketing import outbox as _ob  # noqa: PLC0415

        for item in _ob.read_items_all(root):
            if not isinstance(item, dict) or item.get("kind") != _CAPPED_KIND:
                continue
            ts = _parse_ts(item.get("created_at")) or _parse_ts(item.get("as_of"))
            # An undated row is COUNTED, not skipped. The alternative fails open
            # on exactly the corrupt state a ceiling exists to survive.
            #
            # NO UPPER BOUND, deliberately. The obvious `floor <= ts <= ref`
            # drops rows stamped in the future, and the only things that produce
            # those are clock skew between the daemon host and the runner, and a
            # scheduled item — neither of which makes the volume stop existing.
            # A ceiling that a few seconds of skew can blind is not a ceiling.
            if ts is not None and ts < floor:
                continue
            acct = str(item.get("account") or "").strip()
            if acct:
                counts[acct] = counts.get(acct, 0) + 1
    except Exception as exc:  # noqa: BLE001
        log.warning("wire_routing.breaking_counts unreadable (%s) — no ceiling", exc)
        return {}

    if stamp is not None:
        _COUNT_CACHE[key] = (stamp, dict(counts))
    return counts


@dataclass(frozen=True)
class CapVerdict:
    """Whether ``account`` may take one more breaking item right now."""
    account: str
    allowed: bool
    used: int = 0
    cap: int = 0
    window_hours: int = DEFAULT_BREAKING_WINDOW_HOURS
    #: "" when allowed; else the machine-readable reason a census can group on.
    reason: str = ""
    detail: str = ""
    headroom: int = 0
    fields: dict = field(default_factory=dict)


def breaking_cap_verdict(
    account: str,
    *,
    cfg: dict | None,
    root: Path | str | None = None,
    now: datetime | None = None,
    counts: dict[str, int] | None = None,
) -> CapVerdict:
    """May ``account`` take one more ``kind="breaking"`` item?

    A CAP THAT BINDS MUST NAME ITSELF (house law). The verdict carries the
    account, the number used, the ceiling and the window, and the annotation
    prints all four — an operator who sees the wire go quiet must be able to
    read WHY off one line rather than diffing config against a queue.

    ``counts`` lets a caller resolve the whole roster once and test several
    desks against it (``spill_pool`` does exactly that) instead of re-reading
    the outbox per desk.

    Never raises. An unreadable outbox yields ``allowed=True``: the ceiling is a
    volume brake, and a brake that jams shut on a read error is a worse outage
    than the volume it was fitted to bound.
    """
    acct = str(account or "").strip()
    cap = breaking_cap_for(acct, cfg)
    window = breaking_window_hours(cfg)
    if not acct or cap < 0:
        return CapVerdict(account=acct, allowed=True, cap=cap,
                          window_hours=window, headroom=10 ** 6)
    tally = counts if counts is not None else breaking_counts(
        root, window_hours=window, now=now)
    used = int(tally.get(acct, 0))
    if used < cap:
        return CapVerdict(account=acct, allowed=True, used=used, cap=cap,
                          window_hours=window, headroom=cap - used)
    detail = (f"{acct} has taken {used} kind={_CAPPED_KIND} item(s) in the last "
              f"{window}h against a cap of {cap}")
    _warn_once(
        ("cap", acct, cap, window),
        f"::warning title=wire-volume-cap-reached::{detail} "
        f"(wire_volume.breaking.accounts.{acct}, or default_per_window). "
        f"Further wire items go to another declared wire desk with headroom, or "
        f"park — they do NOT pile onto this desk. Raise the key deliberately if "
        f"this desk really is meant to carry that much relay volume.",
    )
    return CapVerdict(account=acct, allowed=False, used=used, cap=cap,
                      window_hours=window, headroom=0,
                      reason="breaking_cap_reached", detail=detail,
                      fields={"account": acct, "used": used, "cap": cap,
                              "window_hours": window})


def routing_table(cfg: dict | None, *, root: Path | str | None = None) -> dict[str, str]:
    """``{event_class: account}`` AFTER liveness resolution.

    An admin surface must show what is actually IN FORCE, not what the file
    wishes were in force — and under the W5 park default that is no longer
    "the fallback". A class whose configured account is dark now reports THAT
    account, because that is the address its items will carry and where they
    will be found parked; :func:`routing_report` is the richer read that says
    so explicitly. Under the opt-in ``policy: redirect`` the old answer (the
    default account) is still the truthful one.
    """
    return {klass: v.account
            for klass, v in routing_report(cfg, root=root).items()}


def routing_report(cfg: dict | None, *,
                   root: Path | str | None = None) -> dict[str, DeskVerdict]:
    """``{event_class: DeskVerdict}`` — the routing table WITH its park flags.

    Split from :func:`routing_table` rather than changing that function's shape:
    its dict-of-strings contract has readers (admin + the cadence-spine guard)
    and a park is extra information, not a different answer.
    """
    classes = _block(cfg).get("classes")
    if not isinstance(classes, dict):
        return {}
    fallback = default_account(cfg)
    live = _enabled_accounts(cfg, root)
    policy = dark_desk_policy(cfg)
    out: dict[str, DeskVerdict] = {}
    for klass, account in classes.items():
        acct = str(account or "").strip()
        if not acct:
            continue
        # THREE ANSWERS, NOT TWO — the same rule :func:`resolve_desk` applies,
        # and it must be the same rule or the admin view and the dispatch
        # decision disagree about the same config. `live` falsy means UNKNOWN
        # (the accounts model could not be consulted) or NO ROSTER; neither is
        # evidence that `acct` is dark, so the configured owner stands.
        #
        # PRE-W5 THIS FELL BACK TO THE DEFAULT on unknown liveness, and that was
        # correct under the old safety direction ("when in doubt, the historical
        # account"). W5 reverses which direction is safe: the default IS the
        # brand desk, so "when in doubt, give it to flagship" is exactly the
        # donation that made @mastermindx001 a print ticker.
        if not live or acct in live:
            out[str(klass)] = DeskVerdict(account=acct)
        elif policy == "redirect":
            out[str(klass)] = DeskVerdict(account=fallback, redirected=True,
                                          reason="dark_desk_redirect")
        else:
            out[str(klass)] = DeskVerdict(account=acct, parked=True,
                                          reason="dark_desk_parked")
    return out


def spill_pool(cfg: dict | None, *, root: Path | str | None = None) -> list[str]:
    """LIVE accounts that may carry a wire relay, deterministically ordered.

    The roster is DECLARED, never inferred from ``desk_network`` membership:

        wire_routing.spill_accounts: [flagship, mastermind_news]   # explicit
        (absent) -> {wire_routing.default} | set(wire_routing.classes.values())

    The implicit form is the useful default — an account an operator has already
    pointed a wire class at is, by that act, a declared wire owner. The explicit
    key exists so a desk can be made spill-eligible WITHOUT owning a class
    outright (the wire desk that takes overflow but is not the primary for
    anything).

    WHY NOT "every enabled account". Because ``desk_network`` also holds the
    persona desks, and §4's safety rails say wire accounts never take stances.
    A press relay routed to a persona is a voice violation, and it would arrive
    through the one lane whose whole contract is verbatim-with-attribution.
    Volume is not a reason to break the charter, so the pool stays declarative.

    LIVENESS IS THE SAME READ ``route`` USES. Unknown liveness (the accounts
    model could not be consulted) returns ONLY the default — the pre-W4d
    behaviour, and the same fail-closed answer ``route`` gives — because an
    import failure is not evidence that a desk is armed. A dark account is never
    in the returned list.

    The default account always sorts FIRST when it is live (it is the historical
    owner of every class); the rest follow in sorted order so a spill choice is
    reproducible across runs rather than dict-order roulette.

    A DESK AT ITS BREAKING CEILING IS NOT A SPILL TARGET (W5). This function
    answers "may this desk carry a wire relay", and a desk that has already
    taken its window's worth may not — so the ceiling is enforced HERE, at the
    one place the whole lane asks that question, rather than being bolted onto
    each caller. Without it the ceiling would be trivially routable around:
    press_lane's overflow picks the desk with the most headroom from this list,
    so leaving a capped flagship in it would let surplus land on exactly the
    brand desk the cap was fitted to protect. Pass ``root`` — the ceiling reads
    the outbox, and a rootless call cannot count anything.
    """
    fallback = default_account(cfg)
    live = _enabled_accounts(cfg, root)
    if live is None:
        return [fallback]

    block = _block(cfg)
    declared: list[str] = []
    raw = block.get("spill_accounts")
    if isinstance(raw, (list, tuple)):
        declared = [str(a or "").strip() for a in raw]
    else:
        classes = block.get("classes")
        if isinstance(classes, dict):
            declared = [str(a or "").strip() for a in classes.values()]
        declared.append(fallback)

    pool = {a for a in declared if a and a in live}
    # ONE outbox read for the whole roster, not one per desk.
    counts = breaking_counts(root, window_hours=breaking_window_hours(cfg))
    pool = {a for a in pool
            if breaking_cap_verdict(a, cfg=cfg, root=root, counts=counts).allowed}
    ordered = [fallback] if fallback in pool else []
    ordered.extend(sorted(a for a in pool if a != fallback))
    return ordered


def resolve_desk(
    candidate: str,
    *,
    cfg: dict | None,
    root: Path | str | None = None,
    severity: float | None = None,
    fallbacks: tuple[str, ...] = (),
    event_class: Any = None,
) -> DeskVerdict:
    """Liveness + park policy for ONE candidate desk. The W5 seam.

    ROUTING IS STILL NOT LIVENESS — ``candidate`` arrives already decided, by
    ``wire_routing.classes`` in the press lane or by ``severity_account`` on the
    tape. This function only answers what happens when the desk that owns the
    item is not armed, and the answer is now PARK unless config says otherwise:

      * armed        -> DeskVerdict(candidate)                        (silent)
      * dark, park   -> DeskVerdict(candidate, parked=True)           (warned, counted)
      * dark, redirect / severity hatch
                     -> DeskVerdict(<first armed fallback>, redirected=True)

    ``severity`` opens the hatch ONLY when ``dark_desk.severity_exception`` is
    enabled AND the value clears its floor. Both halves are required and both
    default off/high: this is for the single event that genuinely must be seen
    on a live desk tonight, and a lane that passes no severity at all can never
    reach it by accident.

    THREE ANSWERS, NOT TWO, and the distinction is load-bearing.
    ``_enabled_accounts`` returns None when the accounts model could not be
    consulted and an empty set when the config carries no ``desk_network``
    roster at all. Neither is EVIDENCE that ``candidate`` is dark, so both leave
    it untouched and print nothing — parking a correctly-configured desk's
    entire output on the strength of an import failure or a config-less checkout
    (every unit-test fixture is one) would be a self-inflicted outage.

    Never raises.
    """
    acct = str(candidate or "").strip()
    if not acct:
        return DeskVerdict(account=acct)
    try:
        live = _enabled_accounts(cfg, root)
        if not live or acct in live:
            # None (unknown) or empty (no roster) — not proof. See above.
            return DeskVerdict(account=acct)

        hatch = severity_exception(cfg)
        hatch_open = (
            hatch["enabled"] and severity is not None
            and float(severity) >= float(hatch["min_severity"])
        )
        if dark_desk_policy(cfg) == "redirect" or hatch_open:
            ladder = [str(f or "").strip() for f in fallbacks]
            if hatch_open and hatch["to"]:
                ladder.insert(0, hatch["to"])
            ladder.append(default_account(cfg))
            ladder.extend(sorted(live))
            target = next((f for f in ladder if f and f in live), "")
            if not target:
                # Nothing to redirect TO. Parking is the honest answer; inventing
                # a destination would be worse than the dispatch-time park.
                return _park(acct, event_class, unknown=False)
            _warn_dark_redirect(event_class, acct, target, unknown=False)
            return DeskVerdict(account=target, redirected=True,
                               reason=("severity_exception" if hatch_open
                                       else "dark_desk_redirect"),
                               detail=f"{acct} is dark — {target} carries it")
        return _park(acct, event_class, unknown=False)
    except Exception as exc:  # noqa: BLE001 — routing must never break a pass
        log.warning("wire_routing.resolve_desk failed (%s) — keeping %r", exc, acct)
        return DeskVerdict(account=acct)


def _park(acct: str, event_class: Any, *, unknown: bool) -> DeskVerdict:
    """Count + announce a park, and return the verdict that carries it."""
    _PARK_CENSUS[acct] = _PARK_CENSUS.get(acct, 0) + 1
    _warn_dark_park(event_class if event_class is not None else acct, acct,
                    unknown=unknown)
    return DeskVerdict(account=acct, parked=True, reason="dark_desk_parked",
                       detail=f"{acct} is not enabled in desk_network")


def route_verdict(
    event_class: Any,
    *,
    cfg: dict | None,
    root: Path | str | None = None,
) -> DeskVerdict:
    """The full answer to "who takes this wire item, and may they?".

    OWNERSHIP, then LIVENESS, then VOLUME — three questions in that order, and
    keeping them separate is what stops each from quietly re-deciding the others:

      1. ``wire_routing.classes`` names the owner (config, never code).
      2. :func:`resolve_desk` applies the dark-desk policy. Under the ``park``
         default a dark owner KEEPS the item — a brand desk never inherits a
         wire desk's firehose from one switch flip.
      3. :func:`breaking_cap_verdict` applies the rolling per-account ceiling.
         Surplus moves to a DECLARED wire desk that still has headroom
         (``spill_pool``, already ceiling-aware, so a persona desk can never be
         picked and a capped desk is never in the list).

    When the owner is capped and NO wire desk has headroom, the verdict is
    ``parked`` with reason ``breaking_cap_exhausted``. A caller that can refuse
    should refuse; :func:`route`, whose string contract predates this and has
    live callers, degrades to returning the owner and lets the caller's own
    budget/census report it — a ceiling may throttle a desk, it may not silently
    delete an item behind an API that cannot say so.

    Never raises.
    """
    fallback = default_account(cfg)
    classes = _block(cfg).get("classes")
    acct = fallback
    if isinstance(classes, dict):
        acct = str(classes.get(str(event_class)) or "").strip() or fallback

    verdict = resolve_desk(acct, cfg=cfg, root=root, event_class=event_class)
    if verdict.parked:
        return verdict
    acct = verdict.account

    try:
        cap = breaking_cap_verdict(acct, cfg=cfg, root=root)
        if cap.allowed:
            return DeskVerdict(account=acct)
        # `spill_pool` has already dropped every capped desk, so anything left
        # in it has headroom by construction. Ordering is deterministic (the
        # routing default first, then sorted), so a busy tape spreads the same
        # way every run instead of dict-order roulette.
        for target in spill_pool(cfg, root=root):
            if target != acct:
                _warn_once(
                    ("cap-overflow", acct, target),
                    f"::notice title=wire-volume-overflow::{acct!r} is at its "
                    f"rolling kind=breaking ceiling — event_class "
                    f"{event_class!r} is going to {target!r} instead. This is "
                    f"the ceiling working, not a routing change: "
                    f"wire_routing.classes still names {acct!r} as the owner.",
                )
                return DeskVerdict(account=target, redirected=True,
                                   reason="breaking_cap_overflow",
                                   detail=cap.detail)
        _warn_once(
            ("cap-exhausted", acct),
            f"::warning title=wire-volume-exhausted::{cap.detail} — and every "
            f"other declared wire desk is at its ceiling too, so there is "
            f"nowhere with headroom. Wire items are being held. Raise "
            f"wire_volume.breaking, or arm another wire desk and point a "
            f"wire_routing.classes entry at it.",
        )
        return DeskVerdict(account=acct, parked=True,
                           reason="breaking_cap_exhausted", detail=cap.detail)
    except Exception as exc:  # noqa: BLE001 — a ceiling must not break the lane
        log.warning("wire_routing.route_verdict: volume check failed (%s)", exc)
    return DeskVerdict(account=acct)


def route(
    event_class: Any,
    *,
    cfg: dict | None,
    root: Path | str | None = None,
) -> str:
    """The account id that owns a wire emission of ``event_class``.

    The string half of :func:`route_verdict` — kept because press_lane and
    fastlane call it and an account id is all they can act on. Read that
    function's docstring for what the id now means: a dark owner keeps the item
    (it parks at dispatch, reason ``account_disabled``) instead of donating it
    to the routing default, and a capped owner hands it to a wire desk with
    headroom instead of piling on. Never raises.
    """
    return route_verdict(event_class, cfg=cfg, root=root).account
