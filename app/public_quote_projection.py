"""Shared public regular-session quote projector.

Why this exists
----------------
``app/dossier_quote.py`` (the static per-ticker dossier) and
``app/intelligence_hub_market_pulse.py`` (the Intelligence Hub batch route)
both republish ONE thing: a debranded, honesty-checked regular-session quote
tuple built from a raw Terminal Quote Hub row. Before this module that logic
lived only in the dossier, duplicated by hand would have been how the batch
route's honesty law drifted from the dossier's the first time either changed.
This module is the ONE owner of that projection; both callers wrap it with
their own HTTP/schema/rate-limit concerns.

Authority boundary
-------------------
Market-data authority stays with the Terminal Quote Plane. This module owns
no quote store, scheduler, socket or vendor credential — it is a pure
function over an already-fetched row.

Honesty law (the whole point — carried over verbatim from the dossier)
------------------------------------------------------------------------
``freshness`` describes the FEED; ``session`` describes the MARKET. A caller
may only claim "live" when both agree — a measured realtime row *and* an open
regular session. Every uncertainty resolves DOWNWARD:

* a delayed basis is never "live", however recently it was fetched;
* a realtime basis whose own clock has aged past the bound is "stale";
* a missing or unparseable clock is "stale", never assumed fresh;
* an upstream row this module cannot trust raises rather than guessing.

``chg`` upstream is always a PERCENT, never dollars, however plausible a
dollar reading would look; the absolute move is always DERIVED from
price/prevClose, never read as-is from an upstream field of a similar name.
Extended-hours fields (``extPrice``/``extChg``/...) are never read here at
all — regular and extended moves can have opposite signs, and reading either
would let the wrong session's number reach the page.

Debrand law (research/licenses/MASSIVE_ENTITLEMENT_RECORD.md): the vendor is
never named on a public surface. This module never reads or forwards
``source``/``basis``/``anchor_source``/transport fields into its output — the
returned tuple is display-only allowlisted data.

Freshness bounds are deliberately CALLER-CONFIGURABLE. A single dossier page
a reader stares at wants a tight live bound (``app/dossier_quote.py`` keeps
its own, tighter, historical values); a page carrying up to 58 names at once
cannot demand the same per-name cadence without flickering on a healthy but
quiet ticker, so the module defaults to the looser, upstream-consistent
bounds and callers override only when they have a documented reason not to.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

SCHEMA_FRESHNESS = ("live", "delayed", "stale")
SCHEMA_SESSION = ("regular", "pre", "post", "closed")

# The bases that MAY be called realtime. An ALLOWLIST on purpose (see
# app/dossier_quote.py's original note): a denylist of delayed-looking
# substrings is fail-OPEN, and any basis the hub grows tomorrow would sail
# through it unrecognised as live.
_REALTIME_BASES = frozenset({"REALTIME", "LIVE"})

# Session tags that mean `last` is NOT a regular-session print. "closed" is
# deliberately absent — a closed regular session still has a settled regular
# close, and that IS what a regular-view consumer should show.
_EXTENDED_SESSION_TAGS = frozenset({
    "pre", "premarket", "pre-market", "post", "after", "afterhours",
    "after-hours", "extended", "overnight",
})

# How far the hub's own percent may sit from the one implied by
# last/prevClose before we stop trusting it and derive both ourselves.
_PCT_CONSISTENCY_EPSILON = 0.05

# Generic (multi-name / watchlist) freshness bounds — the looser,
# upstream-consistent numbers. See module docstring for why these are looser
# than the dossier's own overrides.
DEFAULT_LIVE_MAX_AGE_SECONDS = 900.0
DEFAULT_STALE_MAX_AGE_SECONDS = 900.0
DEFAULT_CLOSED_STALE_MAX_AGE_SECONDS = 5 * 24 * 3600.0

# The only currency this projector ever emits. The Terminal Quote Plane
# projected here is US-routable-only (freeze §4/§6); a currency field that
# guessed at a glyph for an unrecognised market would be worse than none.
_ALLOWLISTED_CURRENCY = "USD"


class QuoteProjectionError(ValueError):
    """Raised when a row cannot be honestly projected as a regular quote.

    A ``ValueError`` subclass on purpose: every existing caller (dossier_quote)
    already catches bare ``ValueError`` at its API boundary and turns it into
    a 503, so this type can be introduced without touching that call site.
    """


@dataclass(frozen=True)
class PublicQuote:
    """The debranded, honesty-checked public quote tuple.

    ``observed_at``/``received_at`` are Optional in this implementation even
    though the design doc's interface sketch shows ``observed_at: str``: a
    row with no usable source clock still legitimately projects (freshness
    downgrades to "stale"; app/dossier_quote.py has relied on exactly that
    for its 200-with-stale-freshness behavior since before this module
    existed) and inventing an observation time for it would itself be a
    freshness fabrication — the one thing this module exists to refuse.
    """

    symbol: str
    price: float
    change_abs: float | None
    change_pct: float | None
    currency: str | None
    session: str
    freshness: str
    observed_at: str | None
    received_at: str | None
    published_at: str
    regular_session_date: str | None
    revision: str


# ── small pure helpers (exported: both callers use these directly) ─────────

def finite_number(value: Any) -> float | None:
    """Return a finite float, or None. Booleans are rejected on purpose."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def is_realtime_basis(basis: Any) -> bool:
    """True only for a basis we have actually verified means realtime."""
    if not isinstance(basis, str):
        return False  # absent basis is never evidence of realtime
    return basis.strip().upper() in _REALTIME_BASES


def session_of(row: Mapping[str, Any]) -> str:
    """Map the hub's market session onto the four states callers render."""
    raw = row.get("marketSession")
    token = raw.strip().lower() if isinstance(raw, str) else ""
    if token in ("regular", "rth", "open"):
        return "regular"
    if token in ("pre", "premarket", "pre-market"):
        return "pre"
    if token in ("post", "after", "afterhours", "after-hours", "extended"):
        return "post"
    return "closed"


def freshness_of(
    row: Mapping[str, Any],
    *,
    session: str,
    now: float,
    live_max_age_seconds: float = DEFAULT_LIVE_MAX_AGE_SECONDS,
    stale_max_age_seconds: float = DEFAULT_STALE_MAX_AGE_SECONDS,
    closed_stale_max_age_seconds: float = DEFAULT_CLOSED_STALE_MAX_AGE_SECONDS,
) -> str:
    """Classify the FEED. Every uncertain input resolves downward.

    ``now`` MUST be the request/evaluation clock, never ``published_at`` or
    any other projection-time value — freshness is a fact about the SOURCE
    print, and re-deriving it from when the envelope happened to be built
    would let a slow response manufacture staleness (or a fast one hide it).
    """
    stamped = finite_number(row.get("ts"))
    if stamped is None:
        return "stale"  # no clock we can check == no freshness we can claim
    age = now - stamped
    if age < -live_max_age_seconds:
        # A far-future stamp is a broken clock, not a fresh quote.
        return "stale"
    bound = stale_max_age_seconds if session == "regular" else closed_stale_max_age_seconds
    if age > bound:
        return "stale"
    if (
        row.get("live") is True
        and is_realtime_basis(row.get("basis"))
        and age <= live_max_age_seconds
    ):
        return "live"
    return "delayed"


def _observed_at_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    try:
        return (
            datetime.fromtimestamp(ts, tz=timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    except (OverflowError, OSError, ValueError):
        return None


def _revision_fingerprint(*parts: Any) -> str:
    """A deterministic equality fingerprint over source identity/time/values.

    Two projections of the identical underlying print (same symbol, source
    timestamp, price, move, session, freshness) fingerprint identically —
    that equality is what lets a browser controller tell "nothing changed"
    from "this is a genuine correction" (spec §9 ordering law).
    """
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def project_regular_quote(
    row: Mapping[str, Any],
    *,
    ticker: str,
    now: float,
    published_at: str,
    live_max_age_seconds: float = DEFAULT_LIVE_MAX_AGE_SECONDS,
    stale_max_age_seconds: float = DEFAULT_STALE_MAX_AGE_SECONDS,
    closed_stale_max_age_seconds: float = DEFAULT_CLOSED_STALE_MAX_AGE_SECONDS,
) -> PublicQuote:
    """Build the allowlisted public tuple from ONE Terminal regular-view row.

    Raises ``QuoteProjectionError`` (a ``ValueError``) when the row cannot be
    honestly projected: an explicitly extended-session print, or no usable
    positive regular-session price/reference. Callers turn that into their
    own refusal (dossier: 503 for that ticker; batch route: an ``errors``
    entry for that symbol) — this function never guesses a number to avoid
    raising.
    """
    # ``regularSession`` reports the STATE of the regular session, not which
    # session THIS print came from — a closed regular session still legitimately
    # carries the settled regular close. Only an explicit extended tag refuses.
    print_session = row.get("regularSession")
    if isinstance(print_session, str) and print_session.strip().lower() in _EXTENDED_SESSION_TAGS:
        raise QuoteProjectionError(
            f"quote row is an extended-session print: {print_session!r}"
        )

    price = finite_number(row.get("last"))
    if price is None:
        price = finite_number(row.get("close"))
    prev_close = finite_number(row.get("prevClose"))
    if price is None or price <= 0 or prev_close is None or prev_close <= 0:
        raise QuoteProjectionError("row carried no usable regular-session price")

    # The anchor rolls forward once today's session is not yet in hand
    # (prevClose advances to the last close and equals `last`, flattening the
    # naive move to zero). `prevSessionChg` is upstream's own "today is not in
    # hand" signal; when present and usable, reconstruct the anchor from it
    # rather than dividing by (or publishing) a self-referential pair.
    prev_session_pct = finite_number(row.get("prevSessionChg"))
    if prev_session_pct is not None:
        ratio = 1.0 + prev_session_pct / 100.0
        if ratio > 0:
            prev_close = price / ratio

    # `chg` upstream is a PERCENT. The dollar move is always DERIVED, never
    # read from a same-shaped field. The two can legitimately disagree (the
    # hub can select a different anchor at runtime); when they do, both are
    # re-derived from the price pair actually being published so the reader
    # never sees a correct dollar move beside a percent from another session.
    change_abs = price - prev_close
    derived_pct = change_abs / prev_close * 100.0
    change_pct = finite_number(row.get("chg"))
    if change_pct is None or abs(change_pct - derived_pct) > _PCT_CONSISTENCY_EPSILON:
        change_pct = derived_pct

    session_date = row.get("regularSessionDate")
    stamped = finite_number(row.get("ts"))
    session = session_of(row)
    freshness = freshness_of(
        row,
        session=session,
        now=now,
        live_max_age_seconds=live_max_age_seconds,
        stale_max_age_seconds=stale_max_age_seconds,
        closed_stale_max_age_seconds=closed_stale_max_age_seconds,
    )

    symbol = str(ticker or "").strip().upper()
    revision = _revision_fingerprint(
        symbol, stamped,
        round(price, 6), round(change_abs, 6), round(change_pct, 6),
        session, freshness,
    )

    return PublicQuote(
        symbol=symbol,
        price=price,
        change_abs=change_abs,
        change_pct=change_pct,
        currency=_ALLOWLISTED_CURRENCY,
        session=session,
        freshness=freshness,
        observed_at=_observed_at_iso(stamped),
        received_at=None,  # no trustworthy upstream receive clock exists today
        published_at=published_at,
        regular_session_date=session_date if isinstance(session_date, str) else None,
        revision=revision,
    )
