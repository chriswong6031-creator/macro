"""engine.prophet_live.interval — the armed-pack interval contract. ONE reader.

The nightly pack publishes, per name, the price interval over which
:func:`engine.signal_gate.is_buyable` is true. Three things read that interval: the
pack's own build-time parity check, the */5 evaluator, and the G0.1 parity test.
Divergence between any two of them is the exact failure mode gate G0.1 exists to
catch — a level that looks right on both sides and is wrong — so the arithmetic
lives here once and nowhere else.

STDLIB ONLY, deliberately. :mod:`engine.prophet_live.armed_pack` needs pandas to
probe; the */5 lane installs ``pyyaml boto3`` and no pandas. Putting the contract in
the heavy module would make ``import live_states`` raise ModuleNotFoundError on the
lane it exists to serve.
"""
from __future__ import annotations

from typing import Any

#: The probe states, in the order the pack reports them. ``eligible_t4`` means
#: "eligible tonight but NOT in signal_gate.BUYABLE_TIERS" — the T4 tier plus the
#: anticipation-early leg, which is exactly the set the buy boards exclude.
STATES: tuple[str, ...] = ("buyable", "eligible_t4", "near", "dormant", "irregular")


def lower_edge(entry: dict[str, Any]) -> float | None:
    """The buyable interval's lower bound: ``fade_px`` when buyable, else ``trigger_px``.

    The two names carry the same number for opposite situations — below it, a board
    name loses tonight's verdict, and a dormant name gains it — so a consumer that
    needs the boundary rather than the story asks for it here.
    """
    if entry.get("fade_px") is not None:
        return float(entry["fade_px"])
    if entry.get("trigger_px") is not None:
        return float(entry["trigger_px"])
    return None


def interval_contains(entry: dict[str, Any], px: float) -> bool | None:
    """Would the gate call ``px`` buyable for this name? None = the pack cannot say.

    None is returned for an unprobed or irregular name; the intraday lane turns that
    into ``dark`` with a reason rather than guessing a state (G0.3).
    """
    if not entry or entry.get("state") == "irregular":
        return None
    if not entry.get("probed"):
        return None
    in_band = entry.get("buyable_in_band")
    if in_band is None:
        return None
    if not in_band:
        return False
    lo = lower_edge(entry)
    if lo is not None and px < lo:
        return False
    hi = entry.get("fade_hi_px")
    if hi is not None and px > float(hi):
        return False
    return True


def self_check(names: dict[str, dict[str, Any]]) -> list[str]:
    """G0.1 parity: interval membership at the as-of close == tonight's verdict.

    Returns one human-readable line per mismatch (empty list = clean). Unprobed and
    irregular names answer None above and are skipped — they publish no threshold, so
    there is nothing for the evaluator to get wrong.
    """
    bad: list[str] = []
    for tkr, entry in sorted(names.items()):
        want = bool(entry.get("center_buyable"))
        got = interval_contains(entry, float(entry.get("as_of_close") or 0.0))
        if got is None:
            continue
        if got != want:
            bad.append(
                f"{tkr}: interval says buyable={got} at as_of_close="
                f"{entry.get('as_of_close')} but tonight's gate says {want} "
                f"(state={entry.get('state')}, trigger_px={entry.get('trigger_px')}, "
                f"fade_px={entry.get('fade_px')}, fade_hi_px={entry.get('fade_hi_px')})")
    return bad
