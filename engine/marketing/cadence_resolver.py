"""engine.marketing.cadence_resolver — per-account posting cadence (XG-W2).

WHAT THIS REPLACES. ``config/marketing.yml`` sets
``sentinel.max_posts_per_account_per_day: -1`` (operator 2026-07-24, autonomous
cadence). That sentinel is a GLOBAL backstop and it is honest about being one —
it says nothing about who is posting. With one live account that read fine; with
seven it means seven accounts share one unbounded ceiling, and the per-account
``cadence:`` blocks in ``config/personas/<id>.yml`` were decorative (nothing read
them). This module is the per-account law the specs always described:

    the sentinel -1 stays the global backstop it is;
    the resolver bounds each account from ITS OWN spec.

The two compose — an account is allowed to post only when BOTH agree. Lowering
the sentinel back to a real number still binds; raising it does not widen a
persona past its spec. The D08 age ramp narrows the sentinel side per account
(``outbox.effective_cap_for``, #3884), so the full daily-volume bound is
stricter-of(base, tier, spec).

NOT YET COMPOSED (#3884 F6). The ramp tier also carries its own
``min_minutes_between_posts``, and nothing consumes it at post time — this
module reads SPACING from the persona spec alone. A week-1 desk is therefore
tier-bounded on volume and spec-bounded on spacing. Composing them is the
remaining half of the tier-aware cadence contract; it needs the resolver to take
an account age, which is a design decision rather than a patch, so it is named
here instead of being half-built.

DOCTRINE (constitution §13.8 "Adaptive cadence" — the requirements spec).
Cadence should reflect market opportunity, account territory, time zone, recent
topic load, relationship follow-ups, profile needs and output quality. v1 ships
the CONFIG-DRIVEN half of that list, deterministically and with no LLM in the
path:

    time zone / territory  -> ``cadence.session`` (XG-W2, new schema field)
    account territory      -> ``cadence.posts_per_day`` + ``min_spacing_min``
    realism (no clock tell)-> ``cadence.jitter_min``, derived from a seed
    profile needs          -> ``cadence.weekend_shape``

The remaining inputs — market opportunity, recent topic load, relationship
follow-ups, output quality — need signals that do not exist yet. They arrive
with the XG-W5 scoring brain. The seam is explicit and typed: ``resolve()``
takes a ``market_state`` argument that v1 ignores and documents, so wiring the
scorer in later is an implementation change inside this module, not a signature
change at every call site. NOTHING here consults an LLM, and nothing here
escalates: the resolver may only REFUSE or allow, exactly like every other
deterministic gate in the marketing stack.

DETERMINISM. Jitter is derived from ``crc32(seed)``, never from a clock or an
RNG (the same law ``publish.post_jitter_max_min`` already follows in
``scripts/marketing_publisher.py``), so a dry-run and the live run resolve
identically and no test needs to freeze randomness.

STATE. The resolver reads posting history from the state the publisher ALREADY
maintains — the outbox status ledger (``posted``/``posting`` rows). It opens no
new intraday store: the fastlane daemon on the VPS makes zero repo writes and
must keep making zero.

Public API:
    load_profile(account, *, specs=None, root=None) -> CadenceProfile | None
    load_profiles(*, specs=None, root=None)         -> {account: CadenceProfile}
    posting_history(state)                          -> {account: [(dt, kind), …]}
    resolve(...)                                    -> Decision
    resolver_config(cfg)                            -> resolved knob dict
    in_session(profile, when) / daily_budget(...)   -> the two window helpers
    jitter_minutes(seed, jitter_min)                -> deterministic offset
"""
from __future__ import annotations

import logging
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Knobs (defaults; every one overridable from config/marketing.yml)
# ─────────────────────────────────────────────────────────────────────────────

#: ``cadence.weekend_shape`` -> the fraction of ``posts_per_day`` an account may
#: spend on a Saturday/Sunday. Charter §8 law: suggested cadences are HYPOTHESES,
#: so these live in config (``cadence_resolver.weekend_factors``) and these values
#: are only the in-code fallback. A shaped weekend never SILENCES an account —
#: the resolved budget floors at 1 — because "post less at the weekend" is a
#: realism knob, not a kill switch.
_DEFAULT_WEEKEND_FACTORS: dict[str, float] = {
    "light": 1.0 / 3.0,
    "medium": 2.0 / 3.0,
    "full": 1.0,
}

#: Master switch. OFF = the resolver reports its verdict and allows everything
#: (shadow mode), so the wave can land dark and be armed by config.
_DEFAULT_ENABLED = True


def resolver_config(cfg: dict | None) -> dict[str, Any]:
    """Resolve the ``cadence_resolver:`` block from config/marketing.yml.

    Fail-soft: a missing block, a junk value, or a non-dict cfg all fall back to
    the in-code defaults above. Never raises.
    """
    block = {}
    if isinstance(cfg, dict):
        raw = cfg.get("cadence_resolver")
        if isinstance(raw, dict):
            block = raw

    enabled = block.get("enabled", _DEFAULT_ENABLED)
    if not isinstance(enabled, bool):
        enabled = str(enabled).strip().lower() in {"1", "true", "yes"}

    factors = dict(_DEFAULT_WEEKEND_FACTORS)
    raw_factors = block.get("weekend_factors")
    if isinstance(raw_factors, dict):
        for shape, value in raw_factors.items():
            try:
                f = float(value)
            except (TypeError, ValueError):
                log.warning("cadence_resolver: bad weekend_factors.%s=%r — keeping default",
                            shape, value)
                continue
            if 0.0 < f <= 1.0:
                factors[str(shape)] = f
            else:
                log.warning("cadence_resolver: weekend_factors.%s=%r outside (0, 1] — "
                            "keeping default", shape, value)
    return {"enabled": enabled, "weekend_factors": factors}


# ─────────────────────────────────────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SessionWindow:
    """One local-clock window, minutes-from-midnight, half-open [start, end).

    A window whose end is <= its start WRAPS past midnight (``22:00-02:00``),
    which the Asia desks need: Hong Kong's pre-open leg starts the evening
    before New York's date rolls.
    """

    start_min: int
    end_min: int

    def contains(self, minute_of_day: int) -> bool:
        if self.end_min > self.start_min:
            return self.start_min <= minute_of_day < self.end_min
        # Wrapping window.
        return minute_of_day >= self.start_min or minute_of_day < self.end_min


@dataclass(frozen=True)
class CadenceProfile:
    """One account's resolved cadence law, read from its persona spec."""

    account: str
    posts_per_day: int
    min_spacing_min: int
    jitter_min: int
    weekend_shape: str
    #: IANA zone name from ``cadence.session.tz``; "" when the spec declares no
    #: session (the account has no territory clock — everything is in-window).
    tz: str = ""
    windows: tuple[SessionWindow, ...] = ()
    #: How many of the daily budget may land OUTSIDE the declared windows. This
    #: is the weighting mechanism — Cici's 3/day with an allowance of 1 means at
    #: least two of her three posts belong to the Asia session. 0 = the windows
    #: are a hard fence.
    outside_window_posts_per_day: int = 0
    source: str = ""

    @property
    def has_session(self) -> bool:
        return bool(self.tz and self.windows)


def _parse_window(raw: str) -> SessionWindow | None:
    """Parse ``"HH:MM-HH:MM"`` into a SessionWindow. None on anything malformed."""
    try:
        start_s, end_s = str(raw).split("-", 1)
        sh, sm = (int(p) for p in start_s.strip().split(":", 1))
        eh, em = (int(p) for p in end_s.strip().split(":", 1))
    except (AttributeError, TypeError, ValueError):
        return None
    if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 24 and 0 <= em <= 59):
        return None
    start = sh * 60 + sm
    end = eh * 60 + em
    if start == end:
        return None
    return SessionWindow(start_min=start, end_min=end)


def parse_windows(raw: Any) -> tuple[SessionWindow, ...]:
    """Parse a ``session.windows`` list. Malformed entries are DROPPED, not
    guessed — the spec validator in ``personas.py`` is what rejects them loudly;
    here we stay fail-soft so a bad spec cannot crash the publisher."""
    if not isinstance(raw, (list, tuple)):
        return ()
    out = []
    for entry in raw:
        w = _parse_window(entry)
        if w is not None:
            out.append(w)
    return tuple(out)


def profile_from_cadence(account: str, cadence: dict | None, *,
                         source: str = "") -> CadenceProfile | None:
    """Build a CadenceProfile from a persona spec's ``cadence`` block.

    Returns None when the block is unusable — the resolver then ABSTAINS for
    that account (allow, reason ``no_profile``) rather than inventing a bound.
    An account with no spec is governed by the sentinel exactly as before.
    """
    if not isinstance(cadence, dict):
        return None
    try:
        posts_per_day = int(cadence["posts_per_day"])
        min_spacing_min = int(cadence["min_spacing_min"])
        jitter_min = int(cadence.get("jitter_min", 0))
    except (KeyError, TypeError, ValueError):
        return None
    shape = str(cadence.get("weekend_shape") or "full")

    tz = ""
    windows: tuple[SessionWindow, ...] = ()
    outside = 0
    session = cadence.get("session")
    if isinstance(session, dict):
        tz = str(session.get("tz") or "").strip()
        windows = parse_windows(session.get("windows"))
        try:
            outside = int(session.get("outside_window_posts_per_day", 0))
        except (TypeError, ValueError):
            outside = 0
        if not windows:
            tz = ""

    return CadenceProfile(
        account=str(account),
        posts_per_day=posts_per_day,
        min_spacing_min=min_spacing_min,
        jitter_min=max(0, jitter_min),
        weekend_shape=shape,
        tz=tz,
        windows=windows,
        outside_window_posts_per_day=max(0, outside),
        source=source,
    )


def _load_specs(root: Any) -> dict:
    """``{id: PersonaSpec}`` from ``<root>/config/personas/``.

    ROOT-SCOPED on purpose. The publisher already reads ``config/marketing.yml``
    from its ``--root``; reading the persona specs from anywhere else would mean
    a run's cadence law and its posting config came from two different trees.
    ``personas.load_all`` returns ``{}`` for a root with no spec directory, which
    is what makes the resolver ABSTAIN rather than import production cadence into
    a checkout that has none. LAZY import so this module keeps a stdlib-only
    closure at module level.
    """
    try:
        from engine.marketing import personas as _p  # noqa: PLC0415
        return _p.load_all(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("cadence_resolver: persona specs unavailable (%s)", exc)
        return {}


def load_profile(account: str, *, specs: dict | None = None,
                 root: Any = None) -> CadenceProfile | None:
    """Load one account's cadence profile from its committed persona spec.

    ``specs`` is an injectable ``{id: PersonaSpec}`` map (tests, and the caller
    that already loaded them). When None the specs are read from ``root``.
    """
    if specs is None:
        specs = _load_specs(root)
    spec = (specs or {}).get(str(account))
    if spec is None:
        return None
    cadence = getattr(spec, "cadence", None)
    if cadence is None and isinstance(spec, dict):
        cadence = spec.get("cadence")
    return profile_from_cadence(account, cadence,
                                source=str(getattr(spec, "source", "") or ""))


def load_profiles(*, specs: dict | None = None,
                  root: Any = None) -> dict[str, CadenceProfile]:
    """Every account that has a usable cadence profile, keyed by account id."""
    if specs is None:
        specs = _load_specs(root)
    out: dict[str, CadenceProfile] = {}
    for acct in (specs or {}):
        p = load_profile(acct, specs=specs)
        if p is not None:
            out[acct] = p
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Posting history — read from the state the publisher already keeps
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def posting_history(state: dict) -> dict[str, list[tuple[datetime, str]]]:
    """``{account: [(sent_at_utc, kind), ...]}`` from an ``outbox.fold_state()``.

    An item counts as SENT when its folded status is ``posted`` or ``posting``
    ("posting" is in-flight — it likely reached the network, so it holds its
    slot, the same reading ``outbox.posted_today_by_account`` already uses). The
    timestamp is the last applied ledger row's ``at``, which is when the post
    actually went out; ``as_of`` is the GENERATION day and would misdate every
    nightly item by one day.
    """
    items = (state or {}).get("items") or {}
    last = (state or {}).get("last") or {}
    status = (state or {}).get("status") or {}
    out: dict[str, list[tuple[datetime, str]]] = {}
    for iid, item in items.items():
        if status.get(iid, "queued") not in {"posted", "posting"}:
            continue
        ts = _parse_ts((last.get(iid) or {}).get("at"))
        if ts is None:
            continue
        acct = str(item.get("account") or "")
        out.setdefault(acct, []).append((ts, str(item.get("kind") or "")))
    for rows in out.values():
        rows.sort(key=lambda r: r[0])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Local-clock helpers
# ─────────────────────────────────────────────────────────────────────────────

def _local(now: datetime, tz: str) -> datetime:
    """``now`` in the profile's timezone; UTC when no tz or the zone is unknown."""
    aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    if not tz:
        return aware.astimezone(timezone.utc)
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415
        return aware.astimezone(ZoneInfo(tz))
    except Exception as exc:  # noqa: BLE001
        log.warning("cadence_resolver: unknown timezone %r (%s) — using UTC", tz, exc)
        return aware.astimezone(timezone.utc)


def in_session(profile: CadenceProfile, when: datetime) -> bool:
    """True when ``when`` falls inside one of the profile's declared windows.

    An account with no session declared is ALWAYS in session — no territory
    clock means no territory restriction.
    """
    if not profile.has_session:
        return True
    local = _local(when, profile.tz)
    minute = local.hour * 60 + local.minute
    return any(w.contains(minute) for w in profile.windows)


def daily_budget(profile: CadenceProfile, when: datetime, *,
                 weekend_factors: dict[str, float] | None = None) -> int:
    """The account's post budget for the local calendar day of ``when``.

    Weekdays: ``posts_per_day``. Weekends: shaped by ``weekend_shape``, floored
    at 1 (a shaped weekend thins an account, it never silences one).
    """
    local = _local(when, profile.tz)
    if local.weekday() < 5:
        return max(0, int(profile.posts_per_day))
    factors = weekend_factors or _DEFAULT_WEEKEND_FACTORS
    factor = factors.get(profile.weekend_shape, 1.0)
    return max(1, int(round(profile.posts_per_day * factor)))


def _same_local_day(a: datetime, b: datetime, tz: str) -> bool:
    return _local(a, tz).date() == _local(b, tz).date()


def jitter_minutes(seed: str, jitter_min: int) -> int:
    """Deterministic spacing jitter in ``[0, jitter_min]`` from ``crc32(seed)``.

    ADDED to ``min_spacing_min``, never subtracted: jitter exists to break the
    temporal regularity that reads as automation, and a jitter that could
    SHORTEN the spacing floor would be a safety regression dressed as realism.
    Same law and same mechanism as ``publish.post_jitter_max_min``.
    """
    if jitter_min <= 0:
        return 0
    return zlib.crc32(str(seed).encode("utf-8")) % (int(jitter_min) + 1)


# ─────────────────────────────────────────────────────────────────────────────
# Decision
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Decision:
    """The resolver's verdict for one (account, kind, now)."""

    allow: bool
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"allow": self.allow, "reason": self.reason, "detail": dict(self.detail)}

    def __bool__(self) -> bool:  # so `if decision:` reads naturally
        return self.allow


#: Verdict reasons. ``ok`` and ``no_profile`` allow; the rest refuse.
REASON_OK = "ok"
REASON_NO_PROFILE = "no_profile"
REASON_SHADOW = "shadow"
REASON_DAILY_CAP = "daily_cap"
REASON_MIN_SPACING = "min_spacing"
REASON_OUTSIDE_SESSION = "outside_session_window"


def resolve(
    account: str,
    kind: str,
    *,
    now: datetime,
    profile: CadenceProfile | None,
    history: Sequence[tuple[datetime, str]] | Iterable[tuple[datetime, str]] = (),
    cfg: dict | None = None,
    seed: str | None = None,
    market_state: dict | None = None,
) -> Decision:
    """May ``account`` emit a post of ``kind`` at ``now``?

    Args:
        profile: the account's CadenceProfile, or None. None ABSTAINS — the
            resolver never invents a bound for an account with no spec.
        history: ``[(sent_at, kind), ...]`` for THIS account, from
            :func:`posting_history`. Order-insensitive.
        seed:    jitter seed. Defaults to ``"{account}|{local date}"`` so an
            account's spacing jitter is stable within a day and moves between
            days. Pass the item id to jitter per item instead.
        market_state: XG-W5 SEAM — reserved for the scoring brain's
            market-opportunity / topic-load inputs (constitution §13.8's
            remaining cadence dimensions). v1 IGNORES it: adaptive cadence today
            is config-driven windows only, and a resolver that silently guessed
            at market state would be exactly the unmeasured-input failure the
            epistemics law forbids. Accepted now so wiring the scorer later does
            not touch every call site.

    Never raises.
    """
    del market_state  # XG-W5 seam; see the docstring.

    knobs = resolver_config(cfg)
    if profile is None:
        return Decision(True, REASON_NO_PROFILE, {"account": account})

    rows = [(ts, k) for ts, k in history if isinstance(ts, datetime)]
    tz = profile.tz

    # ── 1. Daily budget (local calendar day) ────────────────────────────────
    budget = daily_budget(profile, now, weekend_factors=knobs["weekend_factors"])
    today_rows = [r for r in rows if _same_local_day(r[0], now, tz)]
    posted_today = len(today_rows)

    detail: dict[str, Any] = {
        "account": account,
        "kind": kind,
        "posts_per_day": profile.posts_per_day,
        "daily_budget": budget,
        "posted_today": posted_today,
        "min_spacing_min": profile.min_spacing_min,
        "weekend_shape": profile.weekend_shape,
        "enabled": knobs["enabled"],
    }

    def _verdict(allow: bool, reason: str, extra: dict | None = None) -> Decision:
        d = dict(detail)
        if extra:
            d.update(extra)
        if allow or knobs["enabled"]:
            return Decision(allow, reason, d)
        # Shadow mode: report the verdict the resolver WOULD have returned, but
        # do not bind. The refusal reason is kept so the operator can read what
        # arming would change before arming it.
        d["would_refuse"] = reason
        return Decision(True, REASON_SHADOW, d)

    if budget >= 0 and posted_today >= budget:
        return _verdict(False, REASON_DAILY_CAP)

    # ── 2. Minimum spacing (+ deterministic jitter) ─────────────────────────
    if rows:
        last_ts = max(ts for ts, _ in rows)
        seed_value = seed if seed is not None else f"{account}|{_local(now, tz).date()}"
        jitter = jitter_minutes(seed_value, profile.jitter_min)
        required = int(profile.min_spacing_min) + jitter
        elapsed_min = (now - last_ts).total_seconds() / 60.0
        detail["required_spacing_min"] = required
        detail["jitter_min_applied"] = jitter
        detail["elapsed_min"] = round(elapsed_min, 1)
        # NEGATIVE elapsed is a post BOOKED IN THE FUTURE, and it must refuse
        # just as hard as a recent one. The publisher advances its in-run history
        # to the booked time (now + send jitter), so the item after a jittered
        # post sees elapsed ≈ -7 minutes; a `0 <= elapsed` guard would read that
        # as "no recent post" and wave the whole backlog through — the exact
        # burst the spacing floor exists to prevent.
        if elapsed_min < required:
            return _verdict(False, REASON_MIN_SPACING)

    # ── 3. Session window (territory clock) ─────────────────────────────────
    if profile.has_session and not in_session(profile, now):
        outside_today = sum(1 for ts, _ in today_rows if not in_session(profile, ts))
        detail["outside_window_allowance"] = profile.outside_window_posts_per_day
        detail["outside_window_posted_today"] = outside_today
        detail["session_tz"] = profile.tz
        if outside_today >= profile.outside_window_posts_per_day:
            return _verdict(False, REASON_OUTSIDE_SESSION)

    return _verdict(True, REASON_OK)
