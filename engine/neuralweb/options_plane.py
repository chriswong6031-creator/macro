"""options_structure — the dealer-positioning block of the Neural Web market plane.

Program of record: charting-app ``docs/MARKET_STRUCTURE_CORE_MASTERPLAN_2026-08-01.md`` §6.

Why the gamma regime belongs in the macro brain
-----------------------------------------------
It is a **conditioning variable for every other macro read**, not another signal beside
them. "Risk-on with dealers long gamma" and "risk-on with dealers short gamma below the
flip" are different states with different realized-vol distributions, and the Neural Web
today cannot tell them apart — so a contradiction check between a bullish verdict and a
vol reading is being run without the one variable that decides whether the vol reading
should be believed.

Laws this block obeys
---------------------
**Context, never a gate** (masterplan §6). ``is_context_only`` is already true for the
whole plane; nothing here may be ranked, scored or filtered on by the Terminal.

**Regime-dynamics law** (memory ``regime-dynamics-law``): a regime label never ships bare.
``index_regime`` always travels with ``regime_trend`` and ``regime_velocity_1d``, and the
trend is computed from the published history rather than asserted. When history is too
short to say, the trend is ``"unknown"`` — never silently ``"stable"``, which would read
as a measurement.

**Honesty tiering** (masterplan §4.1): the regime inherits the dealer-sign convention, so
this is Tier B. ``sign_confidence`` is what a consumer should weight it by, and it is the
same tilt statistic the Positioning tab renders — one definition, two surfaces.

Fail-open
---------
Every missing input yields nulls plus a ``gaps[]`` entry. This block runs inside the
nightly plane build; an options hiccup must never take the macro header down.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

__all__ = ["ROOTS", "NEAR_FLIP_PCT", "options_structure_block"]

#: Roots the block summarises, in priority order. SPX first: it is the index whose dealer
#: book actually drives the S&P complex (74% of the notional against ES's 11%), with SPY
#: and QQQ as the liquid proxies a reader recognises.
ROOTS = ("SPX", "SPY", "QQQ")

#: Within this distance of the flip, the regime is reported as ``near_flip`` rather than
#: long or short.
#:
#: Not a cosmetic band. The flip is a modelled level, and close to it the sign of net
#: gamma is decided by the tail of the distribution rather than by the bulk — reporting a
#: crisp "long_gamma" at 0.3% from the flip claims a precision the estimator does not
#: have. 1% is roughly a one-sigma daily move on the index complex, so inside it the
#: regime can genuinely flip intraday without anything about the book changing.
NEAR_FLIP_PCT = 1.0

#: Sessions of history required before a trend is asserted.
_TREND_MIN_SESSIONS = 3

#: |Δ net GEX| below this share of the level reads as noise rather than a trend.
_TREND_FLAT_FRAC = 0.10

#: Share of total gamma sitting in the front expiry above which the OPEX window is flagged.
_OPEX_SHARE_PCT = 35.0


def _f(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _regime(net_gex_bn: float | None, dist_pct: float | None) -> str | None:
    """long_gamma / short_gamma / near_flip, or None when unknowable.

    Distance to the flip decides `near_flip`; the SIGN of net gamma decides the rest.
    Deriving the sign from the distance instead would be wrong whenever the book is
    short gamma above its flip, which happens on put-heavy index books.
    """
    if net_gex_bn is None:
        return None
    if dist_pct is not None and abs(dist_pct) <= NEAR_FLIP_PCT:
        return "near_flip"
    return "long_gamma" if net_gex_bn >= 0 else "short_gamma"


def _trend(history: list[dict] | None, latest_bn: float | None) -> tuple[str, float | None]:
    """(regime_trend, regime_velocity_1d) from the published gex history.

    Trend is about the MAGNITUDE of the dealer position, not its sign: a book going from
    −2bn to −6bn is strengthening its short-gamma regime even though the number fell.
    Comparing raw signed values would report that as "weakening", which is backwards.

    Returns ``("unknown", None)`` when the history is too short to say. Never "stable" by
    default — a default that looks like a measurement is worse than an absence.
    """
    if latest_bn is None or not isinstance(history, list) or len(history) < _TREND_MIN_SESSIONS:
        return "unknown", None
    prev = None
    for row in reversed(history[:-1]):
        if isinstance(row, dict):
            prev = _f(row.get("net_gex_bn"))
            if prev is not None:
                break
    if prev is None:
        return "unknown", None

    velocity = latest_bn - prev
    scale = max(abs(latest_bn), abs(prev))
    if scale <= 0 or abs(abs(latest_bn) - abs(prev)) / scale < _TREND_FLAT_FRAC:
        return "stable", velocity
    return ("strengthening" if abs(latest_bn) > abs(prev) else "weakening"), velocity


def _sign_confidence(by_strike: list[dict] | None) -> float | None:
    """0..1 confidence that the published net-gamma SIGN survives the sign convention.

    Same statistic the Positioning tab's sign-robustness card renders
    (``lib/marketStructure.ts::signSensitivity``): the absolute tilt between call-side and
    put-side gamma. A book whose two sides nearly cancel can flip sign under a small
    change in the dealer assumption; one dominated by a single side cannot.

    Kept identical on purpose — a Neural Web chip and a Terminal card disagreeing about
    how much to trust the same number would be read as two findings.
    """
    if not isinstance(by_strike, list) or not by_strike:
        return None
    call_abs = 0.0
    put_abs = 0.0
    for row in by_strike:
        if not isinstance(row, dict):
            continue
        c = _f(row.get("gamma_call"))
        p = _f(row.get("gamma_put"))
        if c is not None:
            call_abs += abs(c)
        if p is not None:
            put_abs += abs(p)
    total = call_abs + put_abs
    if total <= 0:
        return None
    return round(abs(call_abs - put_abs) / total, 4)


def _expiring_share(by_expiry: list[dict] | None) -> float | None:
    """Percent of total |gamma| carried by the FRONT expiration.

    The number behind the OPEX flag: when most of the book expires at the next date, the
    regime a desk reads today is carried by contracts that are about to disappear.
    """
    if not isinstance(by_expiry, list) or not by_expiry:
        return None
    rows = [r for r in by_expiry if isinstance(r, dict) and _f(r.get("gamma_net")) is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: str(r.get("exp") or ""))
    total = sum(abs(_f(r.get("gamma_net")) or 0.0) for r in rows)
    if total <= 0:
        return None
    front = abs(_f(rows[0].get("gamma_net")) or 0.0)
    return round(front / total * 100.0, 2)


def options_structure_block(
    repo: Path,
    gaps: list[str],
    read_json,
    roots: tuple[str, ...] = ROOTS,
) -> dict:
    """Build the ``options_structure`` block, or an all-null block plus a gap.

    Parameters
    ----------
    repo : Path
        Repository root.
    gaps : list[str]
        Appended to in place, matching the other plane blocks.
    read_json : callable
        The plane builder's own JSON reader, injected so this module inherits its
        error handling rather than duplicating it.
    roots : tuple[str, ...]
        Candidate roots in priority order. The FIRST one with a usable payload wins;
        the rest are reported in ``roots`` so a consumer can see what was considered.
    """
    nulls: dict[str, Any] = {
        "root": None,
        "index_regime": None,
        "regime_trend": "unknown",
        "regime_velocity_1d": None,
        "net_gex_bn": None,
        "dist_to_flip_pct": None,
        "sign_confidence": None,
        "expiring_gamma_share_pct": None,
        "opex_window": None,
        "roots": list(roots),
        "asof": None,
        "stale": None,
    }

    for root in roots:
        path = repo / "data" / "live_flow_out" / "options_hub" / "gex" / f"{root}.json"
        payload = read_json(path)
        if not isinstance(payload, dict):
            continue
        net_gex_bn = _f(payload.get("net_gex_bn"))
        spot = _f(payload.get("spot_ref"))
        flip = _f(payload.get("gamma_flip"))
        if net_gex_bn is None:
            continue

        dist_pct = None
        if flip is not None and spot is not None and spot > 0:
            dist_pct = round((spot - flip) / spot * 100.0, 2)

        trend, velocity = _trend(payload.get("history"), net_gex_bn)
        share = _expiring_share(payload.get("by_expiry"))

        return {
            "root": root,
            "index_regime": _regime(net_gex_bn, dist_pct),
            "regime_trend": trend,
            "regime_velocity_1d": None if velocity is None else round(velocity, 4),
            "net_gex_bn": round(net_gex_bn, 4),
            "dist_to_flip_pct": dist_pct,
            "sign_confidence": _sign_confidence(payload.get("by_strike")),
            "expiring_gamma_share_pct": share,
            "opex_window": None if share is None else bool(share >= _OPEX_SHARE_PCT),
            "roots": list(roots),
            "asof": payload.get("asof"),
            # Freshness is the plane's own judgement, made by the caller against its
            # `now`; carrying a second staleness rule here would let the two disagree.
            "stale": None,
        }

    gaps.append(
        "options_structure: no usable options_hub/gex payload for "
        + "/".join(roots)
    )
    return nulls
