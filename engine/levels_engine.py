"""engine/levels_engine.py — named gamma-level taxonomy + plain-English narration.

Voltick Gamma-Levels program, WP-A1 (see
research/VOLTICK_COMPETITIVE_SWEEP_AND_BUILD_PLAN.md §4/§5/§7). This is the engine
brick — the translation layer that turns one root's dealer-gamma ``by_strike`` payload
into a small vocabulary of *named levels* (Anchor / Call wall / Put wall / Flip /
Cluster / Counter / Void / Trapdoor / Launchpad / Stack), a single-meaning color law
(sticky / slippery + brightness), a net-gamma regime ribbon, and a plain-English note
per node. The Terminal Levels board (WP-A3) consumes the ``levels.v1`` schema next.

Pure + deterministic: given one ``options_hub.gex/v1`` payload (the dict emitted by
``engine.options_hub.compute_gex``) it returns a ``levels.v1`` dict. No I/O, no clock,
no randomness. It NEVER fabricates: a level absent from the input (no walls, no flip)
is emitted as a null node carrying an honest reason, never a made-up strike.

INPUT CONTRACT (``options_hub.gex/v1`` — see engine/options_hub.py:406 compute_gex):
  top-level : spot_ref, net_gex_bn, gamma_flip, call_wall, put_wall, by_strike,
              root, asof, convention, ...
  by_strike : list of rows, each
              {strike, gamma_net, gamma_call, gamma_put,
               delta_net, vanna_net, charm_net}  (all $mn, signed).

DEALER-SIGN PASSPORT (carried, not re-derived — engine/options_hub.py:7-14,
engine/gex_engine.py:115-133):
  sign = +1 calls, -1 puts; the dealer is ASSUMED long calls / short puts. This is an
  UNOBSERVABLE convention, NOT measured dealer inventory — robust for indices, fragile
  for single names (covered-call ETFs / retail call-buying can flip the true sign). So
  ``gamma_net`` carries an assumed sign: positive => "sticky" (dealer hedging leans
  AGAINST moves, price tends to hold), negative => "slippery" (hedging chases, price
  tends to slide). Every level here inherits that passport; nothing below measures
  inventory, and every read is positioning, not prophecy.

DISPLAY-TIER: nothing here ranks, gates, or advises trades. Levels are LOCATIONS where
dealer hedging concentrates, never targets. The words 'signal' and 'validated' are
banned in user-facing strings (house doctrine); narration is educational, not
directional.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "levels.v1"

# Cluster ◆: a strike carrying >= this share of the Anchor's absolute weight.
CLUSTER_FRAC = 0.50
# Void ≋: a strike carrying < this share of the Anchor's absolute weight is "empty".
VOID_FRAC = 0.05
# Void ≋: this many consecutive empty strikes make a run.
VOID_MIN_RUN = 3

# Default green/red palette (the frontend paints; this is a data hint only). Sticky
# green = holds, slippery red = slides. The colorblind swap maps green->blue,
# red->orange so the two never collide for red/green-deficient viewers.
_PALETTE_STD = {"sticky": "green", "slippery": "red"}
_PALETTE_CB = {"sticky": "blue", "slippery": "orange"}


def _num(x: Any) -> float | None:
    """Coerce to float, None on NaN/inf/non-numeric (mirrors options_hub._f intent)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    # NaN != NaN; inf is not a usable weight.
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


def _clean_rows(by_strike: Any) -> list[dict]:
    """Keep only rows with a finite strike AND a finite gamma_net, sorted by strike.

    gamma_net is the load-bearing field (the signed dealer-gamma weight). A row missing
    it cannot be placed in the taxonomy, so it is dropped rather than guessed.
    """
    rows: list[dict] = []
    for r in by_strike or []:
        if not isinstance(r, dict):
            continue
        k = _num(r.get("strike"))
        g = _num(r.get("gamma_net"))
        if k is None or g is None:
            continue
        rows.append({**r, "strike": k, "gamma_net": g})
    rows.sort(key=lambda r: r["strike"])
    return rows


def _round(x: float | None, n: int = 4) -> float | None:
    return None if x is None else round(x, n)


def _sticky(gamma_net: float) -> bool:
    """Color law: positive net dealer gamma => sticky (holds); negative => slippery.

    This inherits the dealer-sign passport verbatim — it is an assumed convention, not
    a measurement of which way dealers are actually positioned.
    """
    return gamma_net > 0.0


def _null_node(role: str, reason: str) -> dict:
    """Honest placeholder for a level the input does not support (never a fake strike)."""
    return {
        "role": role,
        "strike": None,
        "weight": None,
        "sticky": None,
        "brightness": None,
        "note": reason,
    }


def _node(role: str, strike: float, gamma_net: float, anchor_abs: float,
          note: str) -> dict:
    """A located node with the color law applied.

    weight     : the signed dealer-gamma weight at the strike ($mn, from the payload).
    sticky     : True if positive net gamma (holds), False if negative (slides).
    brightness : |weight| / |Anchor weight|, clamped to [0, 1] — the Anchor is 1.0.
    """
    b = abs(gamma_net) / anchor_abs if anchor_abs > 0 else 0.0
    return {
        "role": role,
        "strike": _round(strike),
        "weight": _round(gamma_net),
        "sticky": _sticky(gamma_net),
        "brightness": _round(min(max(b, 0.0), 1.0)),
        "note": note,
    }


# --------------------------------------------------------------------------- #
# flip (reuse the payload's; recompute from by_strike only when absent)
# --------------------------------------------------------------------------- #

def _flip_from_rows(rows: list[dict]) -> float | None:
    """Interpolated price where cumulative dealer gamma (summed from the lowest strike
    upward) crosses from negative to positive.

    This mirrors engine/options_hub._find_gamma_flip / engine/gex_engine._gamma_flip so
    the sign convention is identical; it is used ONLY as a fallback when the payload did
    not carry ``gamma_flip`` (e.g. a thinned or partial board). When the payload has a
    flip we reuse it verbatim and never recompute — one flip definition, one owner.
    """
    if len(rows) < 4:
        return None
    ks = [r["strike"] for r in rows]
    cum = 0.0
    prev_cum = 0.0
    crossings: list[float] = []
    for i, r in enumerate(rows):
        cum += r["gamma_net"]
        if i == 0:
            prev_cum = cum
            continue
        # zero-touch or a sign change between consecutive cumulative sums
        if prev_cum == 0.0 or (prev_cum < 0) != (cum < 0):
            x0, x1, y0, y1 = ks[i - 1], ks[i], prev_cum, cum
            crossings.append(x0 - y0 * (x1 - x0) / (y1 - y0) if y1 != y0 else x0)
        prev_cum = cum
    if not crossings:
        return None
    # nearest crossing to the middle of the ladder (mirrors the payload's nearest-to-spot
    # tiebreak once spot is known; without spot here we take the lowest-strike crossing,
    # which is the true negative->positive boundary the taxonomy cares about).
    return min(crossings)


# --------------------------------------------------------------------------- #
# node builders
# --------------------------------------------------------------------------- #

def _build_anchor(anchor: dict) -> dict:
    return _node(
        "anchor", anchor["strike"], anchor["gamma_net"], abs(anchor["gamma_net"]),
        "Anchor — the day's biggest dealer-gamma magnet (largest |gamma| strike, "
        "OI-based so it's static intent for the session). A location price gravitates "
        "toward, not a target.",
    )


def _build_walls(payload: dict, rows: list[dict], anchor_abs: float) -> list[dict]:
    """Call wall + Put wall.

    Reuse the payload's ``call_wall`` / ``put_wall`` (they already carry the canonical
    dealer-sign convention from options_hub). Emit an honest null node when the payload
    does not report one — never a fabricated strike.
    """
    by_k = {r["strike"]: r for r in rows}
    out: list[dict] = []

    cw = _num(payload.get("call_wall"))
    if cw is not None and cw in by_k:
        g = by_k[cw]["gamma_net"]
        out.append(_node(
            "call_wall", cw, g, anchor_abs,
            "Call wall — the strongest positive-gamma strike above spot (a sticky "
            "ceiling: dealer hedging leans against a push through it).",
        ))
    else:
        out.append(_null_node(
            "call_wall",
            "No call wall in the input (no positive-gamma strike above spot reported).",
        ))

    pw = _num(payload.get("put_wall"))
    if pw is not None and pw in by_k:
        g = by_k[pw]["gamma_net"]
        out.append(_node(
            "put_wall", pw, g, anchor_abs,
            "Put wall — the largest-gamma strike below spot. Often slippery "
            "(negative gamma) — a heavy level, NOT a guaranteed support: a break "
            "below can accelerate rather than hold.",
        ))
    else:
        out.append(_null_node(
            "put_wall",
            "No put wall in the input (no gamma strike below spot reported).",
        ))
    return out


def _build_flip(payload: dict, rows: list[dict], spot: float) -> dict:
    """Flip ⚡ — reuse the payload's gamma_flip; recompute from by_strike only if absent."""
    fp = _num(payload.get("gamma_flip"))
    source = "payload"
    if fp is None:
        fp = _flip_from_rows(rows)
        source = "recomputed"
    if fp is None:
        return _null_node(
            "flip",
            "No gamma flip in the input and none reconstructable from by_strike "
            "(cumulative dealer gamma does not cross zero across the reported strikes).",
        )
    calm_side = "above" if spot is not None and spot >= fp else "below"
    note = (
        f"Flip — the price where cumulative dealer gamma crosses negative->positive. "
        f"Calmer/stickier above it, wilder/slipperier below. Spot is currently "
        f"{calm_side} the flip."
    )
    if source == "recomputed":
        note += " (Reconstructed from by_strike; the payload did not carry a flip.)"
    return {
        "role": "flip",
        "strike": _round(fp),
        "weight": None,  # a flip is a price boundary, not a weighted strike
        "sticky": None,
        "brightness": None,
        "note": note,
    }


def _build_clusters(rows: list[dict], anchor: dict) -> list[dict]:
    """Cluster ◆ — every strike carrying >= CLUSTER_FRAC of the Anchor's |weight|,
    excluding the Anchor itself. Tagged sticky (green) vs slippery (red)."""
    anchor_abs = abs(anchor["gamma_net"])
    if anchor_abs <= 0:
        return []
    out: list[dict] = []
    for r in rows:
        if r["strike"] == anchor["strike"]:
            continue
        if abs(r["gamma_net"]) >= CLUSTER_FRAC * anchor_abs:
            kind = "sticky (a speed bump)" if _sticky(r["gamma_net"]) else "slippery (a fast lane)"
            out.append(_node(
                "cluster", r["strike"], r["gamma_net"], anchor_abs,
                f"Cluster — a secondary heavy strike (>= {int(CLUSTER_FRAC * 100)}% of "
                f"the Anchor's weight), {kind}.",
            ))
    return out


def _build_counter(rows: list[dict], anchor: dict, flip_price: float | None) -> dict:
    """Counter ↘ — the heaviest strike on the opposite side of the gamma-zero/flip from
    the Anchor (the biggest counter-force to the Anchor's pull).

    Boundary priority: the flip price when we have one, else the Anchor's own strike
    (degenerate split so we still surface the biggest level on the far side).
    """
    boundary = flip_price if flip_price is not None else anchor["strike"]
    anchor_above = anchor["strike"] >= boundary
    # opposite side of the boundary from the Anchor
    if anchor_above:
        opp = [r for r in rows if r["strike"] < boundary]
    else:
        opp = [r for r in rows if r["strike"] > boundary]
    opp = [r for r in opp if r["strike"] != anchor["strike"]]
    if not opp:
        return _null_node(
            "counter",
            "No counter strike — no meaningful dealer gamma on the far side of the "
            "flip from the Anchor.",
        )
    top = max(opp, key=lambda r: abs(r["gamma_net"]))
    side = "below" if anchor_above else "above"
    return _node(
        "counter", top["strike"], top["gamma_net"], abs(anchor["gamma_net"]),
        f"Counter — the heaviest strike on the opposite side of the flip from the "
        f"Anchor ({side} it): the far edge of the range and the biggest opposing force.",
    )


def _build_voids(rows: list[dict], anchor: dict) -> list[dict]:
    """Void ≋ — runs of >= VOID_MIN_RUN consecutive strikes each carrying
    < VOID_FRAC of the Anchor's |weight| (near-empty travel zones). Emitted as ranges."""
    anchor_abs = abs(anchor["gamma_net"])
    if anchor_abs <= 0 or len(rows) < VOID_MIN_RUN:
        return []
    thresh = VOID_FRAC * anchor_abs
    voids: list[dict] = []
    run: list[dict] = []

    def _flush(run_rows: list[dict]) -> None:
        if len(run_rows) >= VOID_MIN_RUN:
            lo = run_rows[0]["strike"]
            hi = run_rows[-1]["strike"]
            voids.append({
                "role": "void",
                "strike": None,               # a range, not a single strike
                "strike_lo": _round(lo),
                "strike_hi": _round(hi),
                "n_strikes": len(run_rows),
                "weight": None,
                "sticky": None,
                "brightness": None,
                "note": (
                    f"Void — {len(run_rows)} consecutive near-empty strikes "
                    f"({lo:g}-{hi:g}); little dealer gamma to slow price, so it can "
                    f"travel through this zone quickly."
                ),
            })

    for r in rows:
        if abs(r["gamma_net"]) < thresh:
            run.append(r)
        else:
            _flush(run)
            run = []
    _flush(run)
    return voids


def _build_trapdoors_launchpads(rows: list[dict], anchor_abs: float) -> list[dict]:
    """Trapdoor ⚠ and Launchpad ⤴ — adjacent sticky/slippery pairs.

    Trapdoor : a positive-gamma (sticky) strike sitting directly ABOVE a large
               negative-gamma (slippery) strike -> a break below the sticky shelf can
               accelerate through the slippery strike beneath it.
    Launchpad: the mirror — a slippery (negative) lid sitting directly ABOVE a sticky
               (positive) shelf -> a break up through the lid can run.

    "Directly above/below" = adjacent rows in the strike-sorted ladder. Only pairs
    where BOTH strikes carry meaningful weight (>= CLUSTER_FRAC of the Anchor) qualify,
    so we flag structural accelerants, not noise.
    """
    out: list[dict] = []
    if anchor_abs <= 0:
        return out
    floor = CLUSTER_FRAC * anchor_abs
    for lo, hi in zip(rows, rows[1:]):  # lo < hi by sort order
        g_lo, g_hi = lo["gamma_net"], hi["gamma_net"]
        if abs(g_lo) < floor or abs(g_hi) < floor:
            continue
        upper_sticky = _sticky(g_hi)
        lower_sticky = _sticky(g_lo)
        if upper_sticky and not lower_sticky:
            # sticky shelf (hi) directly above a slippery strike (lo)
            out.append(_node(
                "trapdoor", hi["strike"], g_hi, anchor_abs,
                f"Trapdoor — a sticky shelf at {hi['strike']:g} sitting on top of a "
                f"slippery strike at {lo['strike']:g}: a break below the shelf can "
                f"accelerate downward through the slippery level beneath.",
            ))
        elif (not upper_sticky) and lower_sticky:
            # slippery lid (hi) directly above a sticky shelf (lo)
            out.append(_node(
                "launchpad", lo["strike"], g_lo, anchor_abs,
                f"Launchpad — a sticky shelf at {lo['strike']:g} under a slippery lid "
                f"at {hi['strike']:g}: a break up through the lid can run.",
            ))
    return out


def _build_stacks(nodes: list[dict]) -> list[dict]:
    """Stack ⊕ (confluence) — any strike where >= 2 distinct node roles land."""
    by_strike: dict[float, set[str]] = {}
    for n in nodes:
        k = n.get("strike")
        if k is None:  # flips / voids / null nodes contribute no single strike
            continue
        by_strike.setdefault(k, set()).add(n["role"])
    stacks: list[dict] = []
    for k in sorted(by_strike):
        roles = sorted(by_strike[k])
        if len(roles) >= 2:
            stacks.append({
                "strike": _round(k),
                "roles": roles,
                "note": (
                    f"Stack — {len(roles)} level roles land on {k:g} "
                    f"({', '.join(roles)}): a confluence strike."
                ),
            })
    return stacks


# --------------------------------------------------------------------------- #
# regime ribbon
# --------------------------------------------------------------------------- #

def _regime(payload: dict, rows: list[dict], spot: float | None,
            anchor: dict | None) -> dict:
    """Net-gamma regime ribbon.

    Sum net dealer gamma across the board: positive => "sticky" (range/pin lean),
    negative => "slippery" (trend/overshoot lean). Prefer the payload's headline
    ``net_gex_bn`` (whole-board sum) for the sign; fall back to summing the windowed
    by_strike rows. Emits a one-sentence plain-English ribbon naming spot vs Anchor.
    """
    net_bn = _num(payload.get("net_gex_bn"))
    if net_bn is not None:
        net_gamma = net_bn
        unit = "bn"
    else:
        net_gamma = sum(r["gamma_net"] for r in rows) if rows else 0.0
        unit = "mn"
    label = "sticky" if net_gamma > 0 else "slippery"

    if not rows or anchor is None:
        ribbon = "No dealer-gamma levels available to read."
    else:
        a = anchor["strike"]
        if spot is None:
            where = f"the Anchor sits at {a:g}"
        elif spot >= a:
            where = f"spot ({spot:g}) is above the Anchor at {a:g}"
        else:
            where = f"spot ({spot:g}) is below the Anchor at {a:g}"
        if label == "sticky":
            ribbon = (
                f"Net dealer gamma is positive (sticky): a range/pin lean where hedging "
                f"leans against moves — {where}. Positioning, not prophecy."
            )
        else:
            ribbon = (
                f"Net dealer gamma is negative (slippery): a trend/overshoot lean where "
                f"hedging chases moves — {where}. Positioning, not prophecy."
            )
    return {
        "net_gamma": _round(net_gamma),
        "net_gamma_unit": unit,
        "label": label,
        "ribbon": ribbon,
    }


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #

def compute_levels(gex_payload: dict | None, spot: float | None = None,
                   colorblind: bool = False) -> dict:
    """Transform one root's ``options_hub.gex/v1`` payload into a ``levels.v1`` dict.

    Args:
        gex_payload: the dict emitted by ``engine.options_hub.compute_gex`` (or any
            payload sharing that contract: top-level ``spot_ref``, ``net_gex_bn``,
            ``gamma_flip``, ``call_wall``, ``put_wall`` and a ``by_strike`` list whose
            rows carry ``strike`` + signed ``gamma_net``).
        spot: spot override; defaults to the payload's ``spot_ref``.
        colorblind: when True, the palette hint maps green/red -> blue/orange (data
            only — the frontend paints).

    Returns a ``levels.v1`` dict. Degenerate/empty input yields honest null nodes and an
    empty regime read; it never raises and never invents a strike.
    """
    payload = gex_payload or {}
    root = payload.get("root")
    asof = payload.get("asof")
    src_schema = payload.get("schema")

    if spot is None:
        spot = _num(payload.get("spot_ref"))

    rows = _clean_rows(payload.get("by_strike"))

    palette = dict(_PALETTE_CB if colorblind else _PALETTE_STD)
    palette_hint = {
        "colorblind": bool(colorblind),
        "sticky": palette["sticky"],
        "slippery": palette["slippery"],
        "law": ("sticky = positive net dealer gamma (holds); "
                "slippery = negative net dealer gamma (slides); "
                "brightness 0..1 = |strike weight| / |Anchor weight|."),
    }

    lineage = {
        "source_schema": src_schema,
        "source_asof": asof,
        "source_convention": payload.get("convention"),
        "note": ("Derived from the options_hub GEX by_strike payload. GEX carries the "
                 "dealer-sign passport: an ASSUMED long-call/short-put convention, not "
                 "measured dealer inventory."),
    }

    # ── degenerate input: honest empties, no crash, no fabrication ──────────────
    if not rows:
        nodes = [
            _null_node("anchor", "No by_strike rows in the input — cannot locate an Anchor."),
            _null_node("call_wall", "No by_strike rows in the input."),
            _null_node("put_wall", "No by_strike rows in the input."),
            _null_node("flip", "No by_strike rows in the input."),
            _null_node("counter", "No by_strike rows in the input."),
        ]
        return {
            "schema": SCHEMA,
            "root": root,
            "asof": asof,
            "spot": _round(spot) if spot is not None else None,
            "regime": _regime(payload, rows, spot, None),
            "nodes": nodes,
            "stacks": [],
            "palette_hint": palette_hint,
            "source": lineage,
        }

    # ── Anchor ★ = the largest |gamma_net| strike (the day's biggest magnet) ────
    anchor_row = max(rows, key=lambda r: abs(r["gamma_net"]))
    anchor = {"strike": anchor_row["strike"], "gamma_net": anchor_row["gamma_net"]}
    anchor_abs = abs(anchor["gamma_net"])

    # ── flip (reuse payload; recompute only if absent) — needed for Counter split
    flip_node = _build_flip(payload, rows, spot)
    flip_price = _num(flip_node.get("strike"))

    nodes: list[dict] = []
    nodes.append(_build_anchor(anchor))
    nodes.extend(_build_walls(payload, rows, anchor_abs))
    nodes.append(flip_node)
    nodes.extend(_build_clusters(rows, anchor))
    nodes.append(_build_counter(rows, anchor, flip_price))
    nodes.extend(_build_voids(rows, anchor))
    nodes.extend(_build_trapdoors_launchpads(rows, anchor_abs))

    stacks = _build_stacks(nodes)

    return {
        "schema": SCHEMA,
        "root": root,
        "asof": asof,
        "spot": _round(spot) if spot is not None else None,
        "regime": _regime(payload, rows, spot, anchor),
        "nodes": nodes,
        "stacks": stacks,
        "palette_hint": palette_hint,
        "source": lineage,
    }
