"""engine.prophet_live.interval — the armed-pack interval contract. ONE reader.

The nightly pack publishes, per name, the price interval over which
:func:`engine.signal_gate.is_buyable` is true WHEN THAT PRICE IS APPENDED as the next
session's bar — the construction tonight's nightly will actually run, not a
restatement of the last bar (``armed_pack.probe_series``). Three things read that
interval: the pack's own build-time parity check, the */5 evaluator, and the G0.1
parity test.
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
#: ``stale`` is NOT a verdict: it marks a name for which no gate ran at all (its
#: bars trail the store tip, or the census budget ran out). Those used to report
#: ``dormant``, which made ``meta.states`` count never-evaluated names as an
#: affirmative "nothing here".
STATES: tuple[str, ...] = ("buyable", "eligible_t4", "near", "dormant", "irregular",
                           "stale")


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


def in_probed_band(entry: dict[str, Any], px: float) -> bool:
    """Is ``px`` inside the price range the PUBLISHED band covers for this name?

    OUTSIDE THE BAND THE PACK KNOWS NOTHING, and :func:`interval_contains` would
    happily extrapolate: a board name gapping -30% still satisfies "above fade_px is
    absent, below fade_hi_px is absent, therefore buyable", and a runaway 25% past
    the band top reads the same way even though the real gate rejects it there (the
    not-topped veto). Both were reproduced on a real pack entry. The evaluator asks
    this FIRST and refuses to report a verdict when the answer is no.

    ``band_lo_px`` IS 0 FOR A CROSS-CLASS NAME, AND THAT 0 IS A SENTINEL, NOT A FLOOR
    (W-L0 gate 5, 2026-08-09). Its span starts at the as-of close and runs UP, so the
    pack has measured nothing at all below that close. The 0 used to be defended as
    knowledge — "the centre verdict already says not-buyable for a gate whose product
    structure is a cross UP" — and that argument does not hold:

      * the buyable set this module describes is an INTERVAL, not an up-ray. The pack
        publishes an upper edge (``fade_hi_px``, the not-topped veto) and an
        ``irregular`` state for multi-run structure, so "not buyable at the close" is
        entirely consistent with "buyable below the close" — a name rejected for
        being extended has its buyable region UNDER its own close, exactly where the
        cross-class probe never looks;
      * the centre verdict constrains ONE price. Extending it downward is an
        inference from an assumed shape, and an inference is not a measurement. A
        24-fixture sweep of the real gate (9 down-ladder points each, 198 gate calls)
        found no name buyable below its own close — which makes the inference
        plausible and unrefuted, i.e. precisely the epistemic status that is not
        knowledge. House law: "not found yet" is not "does not exist", and a null
        licenses no affirmative claim.

    So the 0 stays as the published span sentinel — re-probing downward would double
    the cross-class probe cost inside a budget that already caps coverage — and
    :func:`probe_floor` names the real floor instead. ``live_states`` labels a read
    below it ``unknown`` rather than reporting ``dormant``/``near`` there.

    For a name that IS on the board the floor is the real span low, so a -16% board
    name reports no verdict instead of reading forming.
    """
    lo, hi = entry.get("band_lo_px"), entry.get("band_hi_px")
    if lo is None and hi is None:
        # A pack built before the band fields existed: fall back to the old
        # behaviour rather than darking a whole universe on a schema skew.
        return True
    if lo is not None and px < float(lo):
        return False
    if hi is not None and px > float(hi):
        return False
    return True


def probe_floor(entry: dict[str, Any]) -> float | None:
    """The lowest price the pack actually MEASURED for this name. None = it cannot say.

    The honest twin of :func:`in_probed_band`'s lower half. That function answers off
    the PUBLISHED band, whose lower bound is the 0 sentinel for a cross-class name;
    this one answers off what was swept, which for that class starts at the as-of
    close and runs up. A consumer that wants to know whether a price carries a
    measured verdict asks here — the two differ by exactly the region gate 5 exists
    to stop asserting over.

    None for a pack built before the band fields existed: it published no span, so
    there is no floor to name and no honest way to fabricate one. That path keeps
    :func:`in_probed_band`'s schema-skew fallback rather than declaring a whole
    universe unmeasured.
    """
    lo, hi = entry.get("band_lo_px"), entry.get("band_hi_px")
    if lo is None and hi is None:
        return None
    if lo is not None and float(lo) > 0.0:
        return float(lo)
    # The 0 sentinel — the span started AT the as-of close (see in_probed_band). A
    # close is on every entry the pack publishes, so this is a read, not a guess.
    close = entry.get("as_of_close")
    return float(close) if close is not None else None


def interval_contains(entry: dict[str, Any], px: float) -> bool | None:
    """Would the gate call ``px`` buyable for this name? None = the pack cannot say.

    None is returned for an unprobed or irregular name; the intraday lane turns that
    into ``dark`` with a reason rather than guessing a state (G0.3).

    ASK :func:`in_probed_band` FIRST. This function answers from the interval alone and
    will happily extrapolate outside the price range the probe actually swept.
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


def membership_anchor(entry: dict[str, Any]) -> tuple[bool, str]:
    """``(verdict, which)`` the published interval must reproduce at the as-of close.

    THE ANCHOR IS ``probe_center_buyable``, NOT ``center_buyable``. The pack's edges are
    measured by APPENDING a provisional next-session bar (the construction tonight's
    nightly uses), so the only verdict the interval can be held to at the as-of close is
    the one measured that same way. ``center_buyable`` answers a different question —
    "is this name on tonight's board, on the store as it stands" — and the two genuinely
    disagree for a large share of the board once freshness advances a bar (13 of 15
    as-of-buyable names, measured). Checking the interval against it would withhold the
    levels of every correctly-armed board name that flipped, which is a false alarm with
    the same shape as a real one.

    ``center_buyable`` remains the fallback for a pack built before the field existed:
    on those packs the two readings WERE the same number by construction, so it is the
    right answer there and a wrong one nowhere.
    """
    v = entry.get("probe_center_buyable")
    if v is None:
        return bool(entry.get("center_buyable")), "center_buyable"
    return bool(v), "probe_center_buyable"


def membership_mismatches(names: dict[str, dict[str, Any]]) -> dict[str, str]:
    """``{ticker: explanation}`` where the published interval excludes its own anchor.

    A STRUCTURAL check over the assembled payload, not independent evidence of parity —
    see the block comment above ``armed_pack.edge_checks`` for why. It is reachable via
    config (a high ``bisect_iters`` can land a trigger within one 4-dp step of the close),
    so a mismatch withholds THAT name's levels rather than refusing the whole pack:
    darkening every other name over one boundary case is the wrong trade, and the
    per-name path already exists for unverified levels.

    The verdict compared against is :func:`membership_anchor`'s, which names itself in
    the message — a mismatch line has to say WHICH reading it held the interval to, or a
    reader cannot tell a representation bug from a semantics change.

    Unprobed and irregular names answer None and are skipped — they publish no
    threshold, so there is nothing for the evaluator to get wrong.
    """
    bad: dict[str, str] = {}
    for tkr, entry in sorted(names.items()):
        want, anchor = membership_anchor(entry)
        got = interval_contains(entry, float(entry.get("as_of_close") or 0.0))
        if got is None or got == want:
            continue
        bad[tkr] = (
            f"{tkr}: interval says buyable={got} at as_of_close="
            f"{entry.get('as_of_close')} but the gate says {want} there "
            f"({anchor}) (state={entry.get('state')}, "
            f"trigger_px={entry.get('trigger_px')}, "
            f"fade_px={entry.get('fade_px')}, fade_hi_px={entry.get('fade_hi_px')})")
    return bad


def self_check(names: dict[str, dict[str, Any]]) -> list[str]:
    """:func:`membership_mismatches` as a list of lines."""
    return list(membership_mismatches(names).values())
