"""engine/levels_grade.py — grade the named-level board against the next session.

Voltick Gamma-Levels program, WP-C1 (the Track Record). Pure, deterministic grading:
given a sealed ``levels.v1`` board (from engine.levels_engine.compute_levels) and the NEXT
trading session's OHLC bar, it scores each named level on touch — did the Keystone draw
price to it, did the walls contain the close, did a *sticky* level hold or a *slippery*
level break, did the expected-move band hold.

DISPLAY-TIER DOCTRINE
  These are statistics ABOUT THE MAP — how often dealer-positioning levels described what
  price actually did. Positioning, not prophecy. They are NOT a win rate, NOT a strategy,
  and never a buy/sell ranking. Misses are always reported (never dropped). The dealer-sign
  convention behind sticky/slippery is an ASSUMED convention, not measured dealer inventory.

PURE: no I/O, no clock, no store reads. The driver
(scripts/build_levels_track_record.py) reconstructs the historical board, loads the price
bars, and calls grade_board() here. Never raises on degenerate input — it returns an honest
reason instead.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

SCHEMA = "levels_grade.v1"
TR_SCHEMA = "levels_track_record.v1"
TRADING_DAYS = 252.0

# Roles that carry a strike + (usually) a sticky flag and are scored on touch.
# Void is a range (no single strike) and null nodes carry no strike — both skipped.
TOUCH_ROLES: tuple[str, ...] = (
    "anchor", "call_wall", "put_wall", "flip", "cluster", "counter", "trapdoor", "launchpad",
)


# ── ids ────────────────────────────────────────────────────────────────────────

def level_id(root: str, session_date: str, role: str, strike: float | None, idx: int = 0) -> str:
    """Deterministic dedup key for one graded node (root|date|role|strike|idx).

    idx disambiguates multiple same-role nodes on one board (e.g. two clusters).
    """
    s = "" if strike is None else f"{round(float(strike), 4)}"
    key = f"{root}|{session_date}|{role}|{s}|{idx}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def board_id(root: str, session_date: str) -> str:
    return hashlib.sha256(f"{root}|{session_date}".encode()).hexdigest()[:16]


# ── helpers ──────────────────────────────────────────────────────────────────────

def _num(x: Any) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def expected_move_band(
    spot: float | None, median_iv: float | None, band_mult: float, horizon_days: float = 1.0,
) -> tuple[float, float] | None:
    """1-session expected-move band = spot ± spot·iv·sqrt(h/252)·band_mult.

    Returns (lo, hi) or None when spot/iv are unusable. band_mult is the tuned multiplier
    (starts at 1.96 = a 95% two-sided normal band; the driver re-learns it from realized
    range, sticky and slippery cohorts separately).
    """
    s = _num(spot); iv = _num(median_iv); m = _num(band_mult)
    if s is None or s <= 0 or iv is None or iv <= 0 or m is None:
        return None
    sigma = s * iv * math.sqrt(max(horizon_days, 0.0) / TRADING_DAYS)
    return (s - sigma * m, s + sigma * m)


def _touched(strike: float, lo: float, hi: float) -> bool:
    return lo <= strike <= hi


def _same_side(prior_close: float, close: float, strike: float) -> bool:
    """True if `close` finished on the same side of `strike` as `prior_close` started."""
    return (prior_close <= strike and close <= strike) or (prior_close >= strike and close >= strike)


# ── grade one board ──────────────────────────────────────────────────────────────

def grade_board(
    levels_payload: dict | None,
    next_bar: dict | None,
    prior_close: float | None = None,
    median_iv: float | None = None,
    band_mult: float = 1.96,
    prior_bar: dict | None = None,
) -> dict:
    """Grade one ``levels.v1`` board against the next session's OHLC bar.

    next_bar = {date, open?, high, low, close}. prior_close = the board session's close
    (needed to know which side price approached a level from — the hold/break verdict is
    None without it). median_iv = the board's ATM IV for the expected-move band.
    prior_bar = {high, low} of the BOARD session itself — enables the prior-day-extreme
    null (R2.4b); the prevday block is None without it.

    R2.4b nulls and intraday variants (all additive):
      per node — ``null_touched``/``null_held``: the same touch/close-side-hold test run
        on the strike MIRRORED across the board spot (2·spot − strike). Same distance,
        no positioning information: the deterministic equidistant null. ``pierce_pct``:
        how far beyond the level the session's extreme traded (approach side), in % of
        spot, among touched nodes — the threshold-free intraday-hold read.
      per board — ``wall_range_contained`` (the WHOLE next-session range stayed inside
        the walls, stricter than the close test), ``band_close_contained`` (the close
        stayed in the EM band, looser than the range test), and ``prevday``: the
        prior-day high/low graded as pseudo-walls plus their containment rates — the
        structural null every real level must beat.

    Returns a ``levels_grade.v1`` dict:
      { schema, root, session_date, next_date, reason, band_mult,
        board: { spot, next_close, wall_contained, wall_range_contained, band_contained,
                 band_close_contained, anchor_drew, flip_pivot, range_pct, regime,
                 prevday },
        nodes: [ { level_id, role, strike, sticky, touched, held, broke,
                   post_touch_move_pct, null_touched, null_held, pierce_pct } ] }
    reason ∈ ok | empty_board | no_price_data. Never raises.
    """
    root = (levels_payload or {}).get("root")
    session_date = (levels_payload or {}).get("asof") or (levels_payload or {}).get("session_date")
    out: dict[str, Any] = {
        "schema": SCHEMA, "root": root, "session_date": session_date,
        "next_date": (next_bar or {}).get("date"), "reason": "ok",
        "band_mult": _num(band_mult),
        "board": {}, "nodes": [],
    }

    payload_nodes = (levels_payload or {}).get("nodes")
    if not levels_payload or not isinstance(payload_nodes, list) or not payload_nodes:
        out["reason"] = "empty_board"
        return out

    hi = _num((next_bar or {}).get("high"))
    lo = _num((next_bar or {}).get("low"))
    close = _num((next_bar or {}).get("close"))
    if hi is None or lo is None or close is None or hi < lo:
        out["reason"] = "no_price_data"
        return out

    pc = _num(prior_close)
    spot = _num(levels_payload.get("spot")) or _num(levels_payload.get("spot_ref"))
    regime = ((levels_payload.get("regime") or {}) if isinstance(levels_payload.get("regime"), dict) else {}).get("label")

    # per-role idx counter for stable level_ids on multi-node roles (clusters)
    role_idx: dict[str, int] = {}
    call_wall_strike: float | None = None
    put_wall_strike: float | None = None
    anchor_drew = False
    flip_pivot = False

    for node in payload_nodes:
        if not isinstance(node, dict):
            continue
        role = node.get("role")
        if role not in TOUCH_ROLES:
            continue
        strike = _num(node.get("strike"))
        if strike is None:
            continue  # null node (level absent from the board) — nothing to grade
        idx = role_idx.get(role, 0)
        role_idx[role] = idx + 1
        sticky = node.get("sticky")
        if sticky is not None:
            sticky = bool(sticky)

        touched = _touched(strike, lo, hi)
        held: bool | None = None
        broke: bool | None = None
        if touched and pc is not None and role != "flip":
            same = _same_side(pc, close, strike)
            if sticky is True:
                held, broke = same, (not same)
            elif sticky is False:
                broke, held = (not same), same
            # sticky None (undetermined dealer sign): leave hold/break unscored
        post = ((close - strike) / strike * 100.0) if (touched and strike) else None

        # equidistant null: the strike mirrored across the board spot carries the same
        # distance information and zero positioning information
        null_touched: bool | None = None
        null_held: bool | None = None
        if spot is not None and spot > 0:
            mirror = 2.0 * spot - strike
            if mirror > 0:
                null_touched = _touched(mirror, lo, hi)
                if null_touched and pc is not None and role != "flip":
                    null_held = _same_side(pc, close, mirror)

        # intraday trade-through depth on the approach side, in % of spot
        pierce: float | None = None
        if touched and spot is not None and spot > 0 and pc is not None:
            if pc < strike:
                pierce = max(0.0, hi - strike) / spot * 100.0
            elif pc > strike:
                pierce = max(0.0, strike - lo) / spot * 100.0
            else:
                pierce = max(hi - strike, strike - lo, 0.0) / spot * 100.0

        out["nodes"].append({
            "level_id": level_id(root or "", session_date or "", role, strike, idx),
            "role": role, "strike": round(strike, 4), "sticky": sticky,
            "touched": touched, "held": held, "broke": broke,
            "post_touch_move_pct": (round(post, 4) if post is not None else None),
            "null_touched": null_touched, "null_held": null_held,
            "pierce_pct": (round(pierce, 4) if pierce is not None else None),
        })

        if role == "call_wall":
            call_wall_strike = strike
        elif role == "put_wall":
            put_wall_strike = strike
        elif role == "anchor":
            anchor_drew = anchor_drew or touched
        elif role == "flip":
            flip_pivot = flip_pivot or touched

    wall_contained: bool | None = None
    wall_range_contained: bool | None = None
    if call_wall_strike is not None and put_wall_strike is not None:
        wlo, whi = sorted((put_wall_strike, call_wall_strike))
        wall_contained = wlo <= close <= whi
        wall_range_contained = (wlo <= lo) and (hi <= whi)

    band = expected_move_band(spot, median_iv, band_mult)
    band_contained: bool | None = None
    band_close_contained: bool | None = None
    if band is not None:
        band_contained = (lo >= band[0]) and (hi <= band[1])
        band_close_contained = band[0] <= close <= band[1]

    # prior-day extremes as pseudo-walls: the structural null (R2.4b)
    pd_hi = _num((prior_bar or {}).get("high"))
    pd_lo = _num((prior_bar or {}).get("low"))
    prevday: dict | None = None
    if pd_hi is not None and pd_lo is not None and pd_hi >= pd_lo:
        def _null_level(lvl: float) -> tuple[bool, bool | None]:
            t = _touched(lvl, lo, hi)
            h = _same_side(pc, close, lvl) if (t and pc is not None) else None
            return t, h
        hi_t, hi_h = _null_level(pd_hi)
        lo_t, lo_h = _null_level(pd_lo)
        prevday = {
            "high": round(pd_hi, 4), "low": round(pd_lo, 4),
            "high_touched": hi_t, "high_held": hi_h,
            "low_touched": lo_t, "low_held": lo_h,
            "range_contained_close": pd_lo <= close <= pd_hi,
            "range_contained_range": (lo >= pd_lo) and (hi <= pd_hi),
        }

    out["board"] = {
        "spot": (round(spot, 4) if spot is not None else None),
        "next_close": round(close, 4),
        "call_wall": (round(call_wall_strike, 4) if call_wall_strike is not None else None),
        "put_wall": (round(put_wall_strike, 4) if put_wall_strike is not None else None),
        "wall_contained": wall_contained,
        "wall_range_contained": wall_range_contained,
        "band": ([round(band[0], 4), round(band[1], 4)] if band is not None else None),
        "band_contained": band_contained,
        "band_close_contained": band_close_contained,
        "anchor_drew": anchor_drew,
        "flip_pivot": flip_pivot,
        "range_pct": (round((hi - lo) / spot * 100.0, 4) if spot else None),
        "regime": regime,
        "prevday": prevday,
    }
    return out


# ── aggregate many graded boards into a Track Record ─────────────────────────────

def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n > 0 else None


def aggregate_track_record(grades: list[dict], ci_fn=None) -> dict:
    """Pool graded boards into a ``levels_track_record.v1`` summary.

    ci_fn(k, n) -> (lo, hi) | None  (pass engine.grading_stats.wilson_ci). Every rate ships
    with N tested, N missed (shown, never hidden), a Wilson CI, and a sticky/slippery split.
    Per-role verdict:
      anchor  → "drew price to it"     (touched)
      cluster → "held on touch"        (held, among touched)
      counter → "held on touch"        (held, among touched)
      call/put wall → board "close finished inside the walls" (board.wall_contained)
      flip    → "acted as the pivot"   (touched)
      trapdoor/launchpad → "the break ran" (broke, among touched)
    Board metrics: band_contained %, wall_contained %, learned band multiplier.
    """
    def wrap(k: int, n: int) -> dict:
        d = {"rate": _rate(k, n), "n": n, "hits": k, "misses": n - k}
        if ci_fn is not None and n > 0:
            ci = ci_fn(k, n)
            d["ci"] = ([round(ci[0], 4), round(ci[1], 4)] if ci else None)
        return d

    # role → (predicate over a node, restrict-to-touched)
    role_verdict = {
        "anchor": ("drew price to it", lambda nd: nd.get("touched"), False),
        "cluster": ("held on touch", lambda nd: nd.get("held"), True),
        "counter": ("held on touch", lambda nd: nd.get("held"), True),
        "flip": ("acted as the pivot", lambda nd: nd.get("touched"), False),
        "trapdoor": ("the break ran", lambda nd: nd.get("broke"), True),
        "launchpad": ("the break ran", lambda nd: nd.get("broke"), True),
    }

    per_role: dict[str, Any] = {}
    move_by_role: dict[str, list[float]] = {}
    # collect nodes flat, carrying the board regime for the sticky/slippery split
    for role, (label, pred, only_touched) in role_verdict.items():
        pool = []
        full = []  # unrestricted pool — the null pools must not condition on the REAL touch
        for g in grades:
            if g.get("reason") != "ok":
                continue
            for nd in g.get("nodes", []):
                if nd.get("role") != role:
                    continue
                full.append(nd)
                if only_touched and not nd.get("touched"):
                    continue
                pool.append(nd)
        hits = sum(1 for nd in pool if pred(nd))
        n = len(pool)
        st = [nd for nd in pool if nd.get("sticky") is True]
        sl = [nd for nd in pool if nd.get("sticky") is False]
        moves = [nd["post_touch_move_pct"] for nd in pool
                 if nd.get("touched") and nd.get("post_touch_move_pct") is not None]
        null_scored = [nd for nd in full if nd.get("null_held") is not None]
        pierces = [nd["pierce_pct"] for nd in pool
                   if nd.get("touched") and nd.get("pierce_pct") is not None]
        per_role[role] = {
            "label": label,
            **wrap(hits, n),
            "sticky": wrap(sum(1 for nd in st if pred(nd)), len(st)),
            "slippery": wrap(sum(1 for nd in sl if pred(nd)), len(sl)),
            "median_post_touch_move_pct": (round(_median(moves), 4) if moves else None),
            # equidistant-mirror null, held on touch (close-side) — the bar a real level
            # must clear before "held on touch" carries positioning information
            "null_equidistant": wrap(sum(1 for nd in null_scored if nd.get("null_held")),
                                     len(null_scored)),
            "median_pierce_pct": (round(_median(pierces), 4) if pierces else None),
        }

    # board-level metrics
    ok = [g for g in grades if g.get("reason") == "ok"]

    def board_rate(field: str, sub: str | None = None) -> dict:
        vals = []
        for g in ok:
            b = g.get("board", {})
            v = (b.get(sub) or {}).get(field) if sub else b.get(field)
            if v is not None:
                vals.append(bool(v))
        return wrap(sum(vals), len(vals))

    wall_w = board_rate("wall_contained")
    band_w = board_rate("band_contained")
    # walls verdict is board-level; expose it under a synthetic "walls" key too
    per_role["walls"] = {"label": "close finished inside the walls", **wall_w}

    reasons: dict[str, int] = {}
    for g in grades:
        reasons[g.get("reason", "?")] = reasons.get(g.get("reason", "?"), 0) + 1

    return {
        "schema": TR_SCHEMA,
        "n_boards": len(grades),
        "n_boards_graded": len(ok),
        "reasons": reasons,
        "per_role": per_role,
        "board": {
            "band_contained": band_w,
            "wall_contained": wall_w,
            # R2.4b intraday variants + the prior-day structural null
            "wall_range_contained": board_rate("wall_range_contained"),
            "band_close_contained": board_rate("band_close_contained"),
            "prevday": {
                "high_held": board_rate("high_held", "prevday"),
                "low_held": board_rate("low_held", "prevday"),
                "range_contained_close": board_rate("range_contained_close", "prevday"),
                "range_contained_range": board_rate("range_contained_range", "prevday"),
            },
        },
    }


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def learn_band_mult(
    boards: list[dict], target: float = 0.667, lo: float = 0.5, hi: float = 4.0, steps: int = 71,
) -> float | None:
    """Learn the band multiplier whose expected-move band would have contained the next
    session's range in ~`target` of boards.

    boards = list of {spot, median_iv, next_high, next_low}. Sweeps band_mult on a grid and
    returns the smallest multiplier whose containment rate first reaches `target` (or the
    grid value closest to target if never reached). Honest, explainable — no optimizer.
    """
    rows = []
    for b in boards:
        band0 = expected_move_band(b.get("spot"), b.get("median_iv"), 1.0)
        h = _num(b.get("next_high")); l = _num(b.get("next_low")); s = _num(b.get("spot"))
        if band0 is None or h is None or l is None or s is None:
            continue
        half = band0[1] - s  # one-sigma half-width at mult=1
        if half <= 0:
            continue
        # how many sigmas out did the realized range poke?
        need = max((s - l) / half, (h - s) / half)
        rows.append(need)
    if not rows:
        return None
    rows.sort()
    n = len(rows)
    best = None
    best_gap = None
    for i in range(steps):
        m = lo + (hi - lo) * i / (steps - 1)
        contained = sum(1 for need in rows if need <= m) / n
        gap = abs(contained - target)
        if contained >= target:
            return round(m, 4)
        if best_gap is None or gap < best_gap:
            best_gap, best = gap, m
    return round(best, 4) if best is not None else None
