"""Pure join/count core for the live intraday breadth scoreboard.

The poller (``scripts/live_breadth_poller.py``) does the I/O — one Polygon
full-market snapshot per cycle, plus a one-time read of the nightly-baked
per-name thresholds — and this module does the maths, as pure functions with no
network and no filesystem so the join/count logic is unit-testable without a
socket or a store.

The emitted payload MIRRORS the nightly ``breadth_scorecard()`` shape
(scripts/build_site.py) so the surface lane renders the live poll payload and the
baked nightly payload through ONE code path:

    {"asof": iso, "delay_min": int, "session": "rth"|"pre"|"post"|"closed",
     "basis": "poll",
     "tiers": [{key, label:{en,zh}, univ, n, adv, dec, unch, adv_pct,
                pa50, pa200, nh, nl, net_nh}, ...],
     "comp": {n, adv, dec, unch, adv_pct, pa50, pa200, net_nh},
     "meta": {...}}

Unit conventions match the nightly builder exactly:
  - pa50 / pa200 are 0-100 PERCENTAGES (not fractions).
  - adv / dec / unch / nh / nl are integer counts.
  - adv_pct is 100*adv/(adv+dec) over the tier's advancing+declining names
    (unchanged names excluded from that ratio, as the nightly `adv_pct` is).

Epistemics (masterplan §6): DISPLAY-TIER ONLY. This module NEVER writes a store,
never advances a ledger, and emits NO stance wording — the composite carries the
numbers only; "broad/thin/mixed" copy is the surface's job, never the poller's.
Members absent from the snapshot are EXCLUDED from denominators and counted in
``meta.missing`` — never silently treated as unchanged.
"""
from __future__ import annotations

from typing import Any

# Tier key / order / labels / universe — MUST mirror build_site._BREADTH_TIERS.
# (key, namespace, univ_label, (label_en, label_zh)). The `T()` objects in the
# nightly builder are render-time bilingual wrappers; here we emit plain
# {"en":..,"zh":..} dicts (the surface renders either the T() JSON or this dict
# through the same accessor).
BREADTH_TIERS: tuple[tuple[str, str, str, tuple[str, str]], ...] = (
    ("large", "breadth",          "S&P 500", ("Large cap", "大盘")),
    ("mid",   "midcap_breadth",   "S&P 400", ("Mid cap",   "中盘")),
    ("small", "smallcap_breadth", "S&P 600", ("Small cap",  "小盘")),
)


def canonical_symbol(sym: str) -> str:
    """Normalise a Polygon ticker to the breadth close-cache convention.

    The nightly breadth caches store class shares Yahoo-style with a DASH
    (``BRK-B``, ``BF-B``) — see collectors/breadth.py `_repair` (``.`` -> ``-``).
    Polygon snapshot tickers use a DOT (``BRK.B``). One direction only: fold the
    Polygon dot to the cache dash so the join lands. No second mapping is
    invented — this mirrors the sole canonicalisation the breadth lane already
    does.
    """
    return str(sym).strip().upper().replace(".", "-")


def _wmean(tiers: list[dict], key: str) -> float | None:
    """Member-count-weighted mean of a per-tier metric, skipping None tiers.

    Byte-identical semantics to build_site._wmean so the composite pa50/pa200
    match the nightly weighting.
    """
    num = sum(t[key] * t["n"] for t in tiers if t.get(key) is not None)
    den = sum(t["n"] for t in tiers if t.get(key) is not None)
    return num / den if den else None


def compute_tier(
    key: str,
    univ: str,
    label: dict[str, str],
    thresholds: dict[str, dict[str, float]],
    last_by_symbol: dict[str, float],
) -> dict[str, Any]:
    """Join one tier's baked thresholds against live last-prices -> a tier dict.

    Args:
      thresholds: {canonical_symbol: {"prev_close","ma50","ma200","hi52","lo52"}}
        — the nightly-baked per-name levels for THIS tier's members. Any of the
        MA / 52w levels may be None (a member the close cache holds too shallowly
        for a 200DMA); prev_close is required for adv/dec membership.
      last_by_symbol: {canonical_symbol: last_price} from the snapshot join
        (already filtered to this tier's members, canonicalised).

    Counting rules (mirror collectors/breadth.compute on a one-day diff):
      adv  = last > prev_close ; dec = last < prev_close ; unch = last == prev_close
      pa50 = 100 * #(last > ma50) / #(members with a non-None ma50 AND a last)
      pa200 analogous ; nh = last >= hi52 ; nl = last <= lo52
      net_nh = nh - nl

    A member with no live last is NOT counted anywhere here (the caller tallies
    it into meta.missing). ``n`` is the number of members that DID resolve a last
    price (the live denominator), so a half-reported tier reports honest counts.
    """
    adv = dec = unch = 0
    nh = nl = 0
    n = 0
    above50 = base50 = 0          # numerator / denominator for pa50
    above200 = base200 = 0
    for sym, th in thresholds.items():
        last = last_by_symbol.get(sym)
        if last is None:
            continue              # missing member — excluded (caller counts it)
        n += 1
        prev = th.get("prev_close")
        if prev is not None:
            if last > prev:
                adv += 1
            elif last < prev:
                dec += 1
            else:
                unch += 1
        ma50 = th.get("ma50")
        if ma50 is not None:
            base50 += 1
            if last > ma50:
                above50 += 1
        ma200 = th.get("ma200")
        if ma200 is not None:
            base200 += 1
            if last > ma200:
                above200 += 1
        hi52 = th.get("hi52")
        if hi52 is not None and last >= hi52:
            nh += 1
        lo52 = th.get("lo52")
        if lo52 is not None and last <= lo52:
            nl += 1
    adv_dec = adv + dec
    return {
        "key": key,
        "label": dict(label),
        "univ": univ,
        "n": int(n),
        "adv": int(adv),
        "dec": int(dec),
        "unch": int(unch),
        "adv_pct": (100.0 * adv / adv_dec) if adv_dec else None,
        "pa50": (100.0 * above50 / base50) if base50 else None,
        "pa200": (100.0 * above200 / base200) if base200 else None,
        "nh": int(nh),
        "nl": int(nl),
        "net_nh": int(nh - nl),
    }


def build_payload(
    tiers: list[dict[str, Any]],
    *,
    asof: str,
    delay_min: int,
    session: str,
    missing: dict[str, int] | None = None,
    n_snapshot: int | None = None,
) -> dict[str, Any]:
    """Assemble the full display payload from the per-tier dicts.

    The composite (`comp`) is the member-count-weighted roll-up, WITHOUT any
    label / verdict / tone — stance wording stays with the surface (masterplan
    §6; the poller never emits copy). Composite adv_pct is recomputed from the
    summed adv/dec so it matches the nightly composite.
    """
    adv = sum(t["adv"] for t in tiers)
    dec = sum(t["dec"] for t in tiers)
    unch = sum(t["unch"] for t in tiers)
    net_nh = sum(t["net_nh"] for t in tiers)
    adv_dec = adv + dec
    comp = {
        "n": sum(t["n"] for t in tiers),
        "adv": int(adv),
        "dec": int(dec),
        "unch": int(unch),
        "adv_pct": (100.0 * adv / adv_dec) if adv_dec else None,
        "pa50": _wmean(tiers, "pa50"),
        "pa200": _wmean(tiers, "pa200"),
        "net_nh": int(net_nh),
    }
    meta: dict[str, Any] = {"missing": missing or {}}
    if n_snapshot is not None:
        meta["snapshot_names"] = int(n_snapshot)
    return {
        "schema": "live.breadth.v1",
        "asof": asof,
        "delay_min": int(delay_min),
        "session": session,
        "basis": "poll",
        "tiers": tiers,
        "comp": comp,
        "meta": meta,
    }


def empty_payload(*, asof: str, delay_min: int, session: str,
                  note: str = "no data") -> dict[str, Any]:
    """Fail-soft payload: empty tiers + null composite, never a crash.

    Emitted when the snapshot is unavailable (offline / feed down / no key) so a
    strict consumer still parses a well-formed object and falls back to the baked
    nightly numbers. Same top-level keys as `build_payload`.
    """
    comp = {"n": 0, "adv": 0, "dec": 0, "unch": 0, "adv_pct": None,
            "pa50": None, "pa200": None, "net_nh": 0}
    return {
        "schema": "live.breadth.v1",
        "asof": asof,
        "delay_min": int(delay_min),
        "session": session,
        "basis": "poll",
        "tiers": [],
        "comp": comp,
        "meta": {"missing": {}, "note": note},
    }
