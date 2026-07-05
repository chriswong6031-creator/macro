"""Buy Board 2.0 — SHADOW build (site/factordata/us_standouts_v2.json + preview page).

W6-US §W6, US-3. A NON-LIVE shadow artifact: it never touches the live board
(us_standouts.json), the live setups.json, or any linked page. It runs AFTER the
live board in the nightly flow, wrapped so a failure can NEVER break the render.

WHAT IT DOES
------------
Reads the two committed, already-computed US board artifacts —

  * ``site/factordata/us_standouts.json``  (rich rows: conviction verdict,
    composite_z, alpha, and the full compact signal-gate verdict per name)
  * ``site/factordata/setups.json``        (the honest is_buyable T1–T3 set,
    alpha-ranked; slim signal verdict, no conviction)

— UNIONS them into a candidate pool (no price math, no recompute → sub-second),
and applies the product's dual gate + rotation priority:

  WHAT-gate (trajectory / "good to buy"):
      verdict ∉ {Lagging}, composite_z > floor (config default 0, basis: prior),
      medium-term structure intact (weekly_bull + above200 from the signal read).
      The floor is MODULATED — never hard-gated — by group leadership:
      a leading group lowers the bar one notch, a washed-out group raises it.

  WHEN-gate (entry / "good entry, not chasing"):
      signal_gate.is_buyable(signal) as HARD admission — the SAME validated
      MACD-2D × StochRSI-3D confluence (T1–T4) that already guards setups.json,
      now guarding the board people read. Freshness window (cross within the last
      FRESH_SESSIONS), not-topped, extension guard — all read off the committed
      gate verdict, so we inherit the engine's own freshness/topped logic.

Two lanes, VARIABLE width (0..N, zero fill pressure):

  entry_open  — BOTH gates pass, fresh confluence cross.
  setting_up  — WHAT passes AND a cross is IMMINENT (about-to-cross): tier T4,
                or a small positive bars_to_cross, or momentum ε-close to a
                zero-cross. Every setting_up row is flagged provisional: true
                (partial-bucket caveat, audit #22) until the W6 replay validates
                the "about to cross" detector.

Ordering (never a hard gate): group leadership desc → edge percentile desc →
entry freshness. Concentration is surfaced + softly reported, not backfilled.

Sparse EVENT signals (insider / PEAD / 8-K) enter as an OR/max BONUS chip when
present — never renormalised into an average when absent (audit Q4).

Passports: every emitted number carries {basis, frame, freshness, n}. Every row
carries the two glyphs (edge grade colored by verdict; entry state = tier +
freshness) — NO fused 0–100 (that number anti-correlated with alpha; it dies).

FLIP-TO-LIVE is gated on US-2's ledger: v2 replaces the live board only when its
measured precision@k ≥ live. Until then this is unlinked preview only.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from engine import signal_gate
from engine.group_context import GroupContext, READER_CONTRACT
from lib import config
from lib.pages import write_page

log = logging.getLogger("build_stock_board_v2")

# --------------------------------------------------------------------------- #
#  KNOBS — shipped as priors (basis: prior). If research/US_BOARD_MEASUREMENT.md
#  publishes calibrated values, swap these; until then they are documented
#  defaults for US-2's ledger sweep to move on measured precision@k / MAE.
# --------------------------------------------------------------------------- #
KNOBS = {
    # WHAT-gate composite_z floor. basis: prior — the audit's "composite_z > 0"
    # honest-edge cut. The ledger sweep decides the real value.
    "what_floor_z": 0.0,
    # group-leadership modulation of the floor (NEVER a hard gate; the China
    # falsification forbids hard group gates). Leading group lowers the bar by
    # `notch`; washed-out group raises it by `notch`.
    "floor_notch": 0.25,               # basis: prior — one "notch" in z-units
    "leading_lead": 0.45,              # leadership >= this ⇒ lower the floor
    "washedout_lead": -0.45,           # leadership <= this ⇒ raise the floor
    # WHEN-gate freshness: a cross within the last N sessions is "fresh".
    # basis: prior — masterplan default "cross within last 3 sessions".
    "fresh_sessions": 3,
    # about-to-cross (setting_up) proximity read. basis: prior.
    "setting_up_max_btc": 3.0,         # bars_to_cross <= this ⇒ imminent
    # extension guard: skip names already extended far above the entry (chasing).
    # basis: prior — off_high is the % below the 52w high; a name AT its high with
    # no pullback is a chase. We DON'T hard-drop on it (timing ≠ what), we FLAG it.
    "extension_off_high_flag": 0.0,    # off_high >= this (i.e. at/near high) → chase flag
    # soft per-sector concentration report threshold (top-2 sectors share).
    "concentration_warn_share": 0.5,
}

BUYABLE_TIERS = signal_gate.BUYABLE_TIERS          # ("T1","T2","T3") — inherited
SETTING_UP_TIERS = ("T4",)                          # about-to-cross tier

_STD = "us_standouts.json"
_SETUPS = "setups.json"
_OUT = "us_standouts_v2.json"

# verdict prefixes we treat as Lagging (WHAT-gate reject). The engine writes the
# verdict as "<Word> — <explanation>", so we key on the leading word.
_LAGGING_PREFIXES = ("lagging",)


# --------------------------------------------------------------------------- #
#  candidate assembly                                                          #
# --------------------------------------------------------------------------- #
def _load(site, name):
    p = site / "factordata" / name
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("v2: could not read %s (%s)", name, e)
        return None


def _candidates(std: dict | None, setups: dict | None) -> list[dict]:
    """Union the two board pools into one candidate list, keyed by ticker.

    us_standouts rows are RICH (conviction verdict/composite_z/alpha). setups
    rows are SLIM (signal-only). We prefer the rich row; a setups-only name gets
    a stub with what setups carries (alpha, sector, signal) and a
    ``conviction_missing`` flag so the WHAT-gate can shrink toward the group
    prior rather than silently pass/fail on absent fields.
    """
    by_tkr: dict[str, dict] = {}
    for r in (std.get("buy", []) if std else []) + \
             (std.get("watch", []) if std else []) + \
             (std.get("laggards", []) if std else []):
        t = r.get("ticker")
        if t and t not in by_tkr:
            r = dict(r)
            r["_source"] = "standouts"
            by_tkr[t] = r
    for r in (setups.get("buy", []) if setups else []):
        t = r.get("ticker")
        if not t:
            continue
        if t in by_tkr:
            # already have the rich row; note it was ALSO in the honest setups set
            by_tkr[t]["_in_setups"] = True
        else:
            r = dict(r)
            r["_source"] = "setups"
            r["_in_setups"] = True
            r["_conviction_missing"] = True
            by_tkr[t] = r
    return list(by_tkr.values())


# --------------------------------------------------------------------------- #
#  gates                                                                        #
# --------------------------------------------------------------------------- #
def _verdict_word(conviction: dict | None) -> str:
    v = (conviction or {}).get("verdict") or ""
    return v.strip().split(" ")[0].lower() if v else ""


def _what_gate(row: dict, leadership: float) -> dict:
    """WHAT-gate: trajectory / good-to-buy. Returns {pass, floor, reasons, ...}.

    verdict ∉ {Lagging}; composite_z > floor (floor MODULATED by group leadership,
    never hard-gated by it); medium-term structure intact.
    """
    conv = row.get("conviction") or {}
    conv_missing = bool(row.get("_conviction_missing"))
    reasons: list[str] = []

    # floor modulation by group leadership (soft; the ONLY influence group state
    # has on admission is nudging this bar — the China-falsification guardrail).
    floor = KNOBS["what_floor_z"]
    if leadership >= KNOBS["leading_lead"]:
        floor -= KNOBS["floor_notch"]
        reasons.append("leading group → floor lowered")
    elif leadership <= KNOBS["washedout_lead"]:
        floor += KNOBS["floor_notch"]
        reasons.append("washed-out group → floor raised")

    vword = _verdict_word(conv)
    not_lagging = vword not in _LAGGING_PREFIXES

    z = conv.get("composite_z")
    sig = row.get("signal") or {}
    # Structure read. The RICH (us_standouts) signal carries above200 + weekly_bull.
    # The SLIM (setups) signal does NOT — but a name only reaches setups.json by
    # PASSING the same is_buyable confluence cascade, which already requires
    # long-bias / above-trend for its buyable tiers. So a missing structure field
    # on a buyable setups row is "implicitly attested", not "failed": treat it as
    # intact rather than defaulting to False (which silently emptied the lane).
    has_struct_fields = ("above200" in sig) and ("weekly_bull" in sig)
    if has_struct_fields:
        structure = bool(sig.get("above200")) and bool(sig.get("weekly_bull"))
    else:
        structure = bool(sig.get("eligible")) and (sig.get("tier_cascade") is not None)
        if structure:
            reasons.append("structure implicit (buyable cascade)")

    if conv_missing:
        # setups-only name: no conviction verdict. Shrink toward the GROUP prior
        # (borrow strength) rather than pass/fail on absent fields — a leading
        # group carries it, a neutral/negative group does not.
        z_pass = leadership > KNOBS["washedout_lead"]   # reject only outright washed-out groups
        z = None
        reasons.append("conviction absent → group-prior shrink")
        verdict_pass = leadership > KNOBS["washedout_lead"]
    else:
        z_pass = (z is not None) and (z > floor)
        verdict_pass = not_lagging

    passed = bool(verdict_pass and z_pass and structure)
    return {
        "pass": passed,
        "floor": round(floor, 3),
        "composite_z": z,
        "verdict_word": vword or None,
        "not_lagging": verdict_pass,
        "z_pass": z_pass,
        "structure_intact": structure,
        "conviction_missing": conv_missing,
        "reasons": reasons,
    }


def _fresh_bars(sig: dict) -> int | None:
    """Bars since the confluence cross — smallest of the native ticks and the
    §7-marker fresh_bars the gate already computed."""
    cands = [sig.get("ticks"), sig.get("fresh_bars")]
    vals = [c for c in cands if isinstance(c, (int, float))]
    return int(min(vals)) if vals else None


def _when_gate(row: dict) -> dict:
    """WHEN-gate: entry / good-entry-not-chasing. is_buyable as HARD admission,
    plus freshness + not-topped + extension flag — all off the committed verdict."""
    sig = row.get("signal") or {}
    buyable = signal_gate.is_buyable(sig)      # eligible & tier_cascade in T1/T2/T3
    tier = sig.get("tier_cascade")
    fresh_bars = _fresh_bars(sig)
    fresh = (fresh_bars is None) or (fresh_bars <= KNOBS["fresh_sessions"])
    # not-topped: the gate already drops topped names (tier→None); a live buyable
    # tier is by construction not-topped. We also veto a hard 'block' last marker.
    last = sig.get("last") or {}
    blocked = last.get("quality") == "block"
    off_high = row.get("off_high")
    extended = isinstance(off_high, (int, float)) and off_high >= KNOBS["extension_off_high_flag"]
    passed = bool(buyable and fresh and not blocked)
    return {
        "pass": passed,
        "buyable": buyable,
        "tier": tier,
        "provisional": bool(sig.get("provisional")),   # T3 partial-bucket basis (W6 #22)
        "fresh_bars": fresh_bars,
        "fresh": fresh,
        "blocked": blocked,
        "block_reason": last.get("reason") if blocked else None,
        "extended_flag": extended,     # a FLAG (chase caution), not a gate
        "off_high": off_high,
    }


def _about_to_cross(row: dict) -> dict:
    """SETTING_UP proximity read (provisional). About-to-cross iff the gate's own
    projected tier fires (T4), OR a small positive bars_to_cross, OR the signal is
    'early_now'. This reuses the engine's projection machinery where present and a
    principled proximity read otherwise (audit #22 — provisional until replay)."""
    sig = row.get("signal") or {}
    tier = sig.get("tier_cascade")
    btc = sig.get("bars_to_cross")
    early = bool(sig.get("early_now"))
    by_tier = tier in SETTING_UP_TIERS
    by_btc = isinstance(btc, (int, float)) and 0 < btc <= KNOBS["setting_up_max_btc"]
    imminent = bool(by_tier or by_btc or early)
    how = []
    if by_tier:
        how.append(f"projected {tier}")
    if by_btc:
        how.append(f"~{btc:g} bars to cross")
    if early:
        how.append("early advance-warning")
    return {"imminent": imminent, "bars_to_cross": btc, "tier": tier,
            "early": early, "how": ", ".join(how) or None}


# --------------------------------------------------------------------------- #
#  event bonus (sparse; OR/max, never renormalised)                            #
# --------------------------------------------------------------------------- #
def _event_bonus(row: dict) -> dict | None:
    """Sparse insider/PEAD/8-K edge as an OR/max BONUS chip when PRESENT — never
    averaged in when absent (audit Q4). Reads the conviction trust_tier + drivers
    that the composite already surfaces; emits a single chip if an event edge is
    live, else None (so the row's leadership/edge is not diluted)."""
    conv = row.get("conviction") or {}
    tt = conv.get("trust_tier") or {}
    drivers = conv.get("drivers") or []
    # the engine tags an event-edge name with trust_tier.tier == 'event-edge'
    if tt.get("tier") == "event-edge":
        return {"label": "Event edge (insider/PEAD/8-K)", "tone": "pos",
                "why": tt.get("en")}
    if "selection" in drivers:      # selection leg is the insider/revision stack
        return {"label": "Selection edge", "tone": "pos", "why": None}
    return None


# --------------------------------------------------------------------------- #
#  glyphs + passports                                                          #
# --------------------------------------------------------------------------- #
def _edge_glyph(row: dict, edge_pctile: float | None) -> dict:
    """EDGE grade glyph — the name+group edge percentile, COLORED BY VERDICT
    (never green on a Lagging name; the audit's central honesty fix). No 0-100."""
    conv = row.get("conviction") or {}
    vword = _verdict_word(conv)
    # verdict drives the COLOR; percentile drives the GRADE letter
    if vword == "lagging":
        tone = "neg"
    elif vword in ("high-confluence", "constructive"):
        tone = "pos"
    else:
        tone = "neutral"
    if edge_pctile is None:
        grade = "—"
    elif edge_pctile >= 0.80:
        grade = "A"
    elif edge_pctile >= 0.60:
        grade = "B"
    elif edge_pctile >= 0.40:
        grade = "C"
    else:
        grade = "D"
    return {"grade": grade, "tone": tone, "pctile": edge_pctile,
            "verdict": conv.get("verdict")}


def _entry_glyph(when: dict, setup: dict | None) -> dict:
    """ENTRY state glyph — tier badge + freshness (the "when"). Separate from the
    edge glyph so the two dimensions never fuse into one number."""
    if when["pass"]:
        fb = when["fresh_bars"]
        fresh_lbl = "just crossed" if (fb is not None and fb <= 1) else (
            f"{fb} bars ago" if fb is not None else "fresh")
        return {"tier": when["tier"], "state": "entry_open",
                "freshness": fresh_lbl, "tone": "pos"}
    if setup and setup["imminent"]:
        return {"tier": setup["tier"], "state": "about_to_cross",
                "freshness": setup["how"], "tone": "warm"}
    return {"tier": when.get("tier"), "state": "no_entry",
            "freshness": None, "tone": "neutral"}


def _passport(basis: str, frame: str, freshness, n) -> dict:
    return {"basis": basis, "frame": frame, "freshness": freshness, "n": n}


# --------------------------------------------------------------------------- #
#  build one row                                                               #
# --------------------------------------------------------------------------- #
def _build_row(row: dict, ctx: dict, lane: str, when: dict, what: dict,
               setup: dict | None, edge_pctile: float | None) -> dict:
    conv = row.get("conviction") or {}
    event = _event_bonus(row)
    chips = list(ctx.get("chips") or [])
    if event:
        chips = [event] + chips           # event bonus leads the chip row when present
    if when.get("extended_flag"):
        chips.append({"label": "Chase caution (at/near high)", "tone": "warn",
                      "src": "extension"})
    freshness = ctx.get("passport", {}).get("freshness")
    return {
        # --- row-identity fields (MIRROR us_standouts so US-2's ledger can grade) ---
        "ticker": row.get("ticker"),
        "name": row.get("name"),
        "sector": row.get("sector"),
        "lane": lane,
        # rank filled by the caller after ordering
        "rank": None,
        "gates_passed": {"what": what["pass"], "when": when["pass"],
                         "in_setups": bool(row.get("_in_setups"))},
        # --- the two glyphs (NO fused 0-100) ---
        "edge_glyph": _edge_glyph(row, edge_pctile),
        "entry_glyph": _entry_glyph(when, setup),
        # --- group / rotation context ---
        "leadership": ctx.get("leadership"),
        "group_state": ctx.get("state"),
        "chips": chips,
        "surfaced_by": ctx.get("surfaced_by") or [],
        # --- gate detail (audit / template) ---
        "what": what,
        "when": {k: when[k] for k in
                 ("buyable", "tier", "fresh_bars", "fresh", "blocked",
                  "block_reason", "extended_flag", "off_high")},
        "event_bonus": event,
        # audit #22 — partial-bucket caveat: every SETTING_UP row, plus an ENTRY-OPEN T3
        # (the replay measured T3 fresh fires repainting at 23.8% US / 15.1% CN)
        "provisional": lane == "setting_up" or bool(when.get("provisional")),
        # --- edge inputs ---
        "alpha": row.get("alpha"),
        "composite_z": conv.get("composite_z"),
        "verdict": conv.get("verdict"),
        "off_high": row.get("off_high"),
        "price": row.get("price"),
        # --- per-row passports ---
        "passports": {
            "edge": _passport("name+group-percentile", "cross-sectional",
                              freshness, ctx.get("passport", {}).get("n")),
            "entry": _passport("confluence-gate", "daily",
                               when.get("fresh_bars"), None),
            "group": ctx.get("passport"),
        },
    }


# --------------------------------------------------------------------------- #
#  ordering + concentration                                                    #
# --------------------------------------------------------------------------- #
def _order(rows: list[dict]) -> list[dict]:
    """group leadership desc → edge percentile desc → entry freshness (fresher
    first). NEVER a terminal re-sort by slot/status (kills entry_open_first)."""
    def key(r):
        lead = r.get("leadership") or 0.0
        pct = (r.get("edge_glyph") or {}).get("pctile")
        pct = pct if pct is not None else 0.0
        fb = (r.get("entry_glyph") or {}).get("tier")  # placeholder; real freshness below
        fresh = r.get("when", {}).get("fresh_bars")
        fresh = fresh if isinstance(fresh, (int, float)) else 99
        return (-lead, -pct, fresh)
    out = sorted(rows, key=key)
    for i, r in enumerate(out):
        r["rank"] = i + 1
    return out


def _concentration(rows: list[dict], site=None) -> dict:
    """Surface concentration (top-2 sector share, effective bets) — NOT capped
    away. Leadership-driven concentration is intentional rotation-following.

    W4 (reflexivity overlay, R-B ruling): effective_bets is now computed via the
    similarity-based participation-ratio (membership-Jaccard + high-tier-factor-cosine)
    from engine.reflexivity, superseding the sector-only HHI proxy.  The field name
    is preserved for consumer compatibility.  The basis string is updated so readers
    know what the number means.  If the reflexivity engine is unavailable (missing
    betas / membership), we fall back to the sector-only HHI with a degraded basis
    flag — never a crash, never two divergent numbers.
    """
    from collections import Counter
    n = len(rows)
    secs = Counter(r.get("sector") or "?" for r in rows)
    top2 = sum(c for _, c in secs.most_common(2))
    top2_share = round(top2 / n, 3) if n else 0.0

    # ── W4 similarity-based effective bets (supersedes sector-only HHI) ──
    effective_bets = 0.0
    effective_bets_basis = "none"
    if n >= 2:
        try:
            import json as _json
            from pathlib import Path as _Path
            from engine.reflexivity import (
                build_groups_index, pairwise_similarity, n_eff_participation_ratio,
            )
            _site = site or (config.ROOT / "site")
            # Load betas index (may be absent on first run)
            _betas_path = _site / "factor_betas.json"
            _betas_index: dict = {}
            if _betas_path.exists():
                _raw = _json.loads(_betas_path.read_text())
                if isinstance(_raw.get("betas"), dict):
                    _betas_index = _raw["betas"]
            # Load membership (gitignored, may be absent on CI)
            _mem_path = config.ROOT / "data" / "baskets" / "membership.json"
            _mem_data = None
            if _mem_path.exists():
                _mem_data = _json.loads(_mem_path.read_text())
            # Build groups index from row sector fields + baskets membership
            _tickers = [r.get("ticker", "").upper() for r in rows if r.get("ticker")]
            _sector_by = {r.get("ticker", "").upper(): r.get("sector") or ""
                          for r in rows if r.get("ticker")}
            _groups = build_groups_index(_mem_data, _tickers, _sector_by)
            import numpy as _np
            _S, _, _ = pairwise_similarity(_tickers, _groups, _betas_index)
            _neff = n_eff_participation_ratio(_S)
            effective_bets = round(float(_neff), 1)
            effective_bets_basis = "membership-jaccard+high-tier-factor-cosine"
        except Exception as _e:  # noqa: BLE001
            # Fallback: sector-only HHI (degraded — never crash)
            log.debug("_concentration: reflexivity N_eff failed (%s); using sector HHI", _e)
            if n:
                shares = [c / n for c in secs.values()]
                effective_bets = round(1.0 / sum(s * s for s in shares), 1)
            effective_bets_basis = "sector-only-hhi-fallback"
    elif n == 1:
        effective_bets = 1.0
        effective_bets_basis = "single-candidate"

    return {
        "n": n,
        "n_sectors": len(secs),
        "top2_sector_share": top2_share,
        "effective_bets": effective_bets,
        "effective_bets_basis": effective_bets_basis,
        "by_sector": dict(secs.most_common()),
        "concentrated": bool(top2_share >= KNOBS["concentration_warn_share"] and n >= 4),
    }


# --------------------------------------------------------------------------- #
#  compute                                                                     #
# --------------------------------------------------------------------------- #
def compute(site=None) -> dict:
    site = site or (config.ROOT / "site")
    std = _load(site, _STD)
    setups = _load(site, _SETUPS)
    as_of = (std or {}).get("as_of") or (setups or {}).get("as_of") \
        or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    gc = GroupContext(site=site)
    cands = _candidates(std, setups)

    # edge percentile: within THIS candidate pool, rank by composite_z (the honest
    # edge — the audit's monotone-in-edge number), so the glyph grade is relative.
    zs = sorted(c.get("conviction", {}).get("composite_z") for c in cands
                if isinstance(c.get("conviction", {}).get("composite_z"), (int, float)))
    import bisect

    def edge_pctile(row):
        z = (row.get("conviction") or {}).get("composite_z")
        if not isinstance(z, (int, float)) or not zs:
            return None
        return round(bisect.bisect_right(zs, z) / len(zs), 3)

    entry_open, setting_up = [], []
    for row in cands:
        ctx = gc.for_name(row.get("ticker", ""), row.get("sector"))
        lead = ctx.get("leadership") or 0.0
        what = _what_gate(row, lead)
        when = _when_gate(row)
        setup = _about_to_cross(row)
        pct = edge_pctile(row)
        if what["pass"] and when["pass"]:
            entry_open.append(_build_row(row, ctx, "entry_open", when, what, setup, pct))
        elif what["pass"] and setup["imminent"]:
            setting_up.append(_build_row(row, ctx, "setting_up", when, what, setup, pct))
        # else: dropped (variable width — zero fill pressure, no backfill)

    entry_open = _order(entry_open)
    setting_up = _order(setting_up)

    return {
        "status": "ok",
        "as_of": as_of,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shadow": True,
        "note": ("SHADOW artifact — Buy Board 2.0 (W6-US). Dual-gated (WHAT trajectory "
                 "+ WHEN validated confluence) with rotation-priority ordering. Not live; "
                 "graded in parallel until precision@k >= live board."),
        "universe": len(cands),
        "lanes": {
            "entry_open": entry_open,
            "setting_up": setting_up,
        },
        "counts": {"entry_open": len(entry_open), "setting_up": len(setting_up),
                   "candidates": len(cands)},
        "concentration": {
            "entry_open": _concentration(entry_open, site=site),
            "setting_up": _concentration(setting_up, site=site),
        },
        "knobs": KNOBS,
        "knobs_basis": "prior",          # calibrate via US-2's ledger (US_BOARD_MEASUREMENT.md)
        "reader_contract": {"version": READER_CONTRACT["version"],
                            "sources": list(READER_CONTRACT["sources"])},
        "rotation_coverage": gc.source_passport(),
        "board_passport": _passport("dual-gate+rotation-priority", "cross-sectional",
                                    None, len(cands)),
        # ledger hook: the row-identity fields US-2's grader needs (mirrors
        # us_standouts). If scripts/grade_us_board.py exists it can register this
        # artifact directly; else this documents the contract.
        "ledger": {
            "artifact": "site/factordata/us_standouts_v2.json",
            "row_identity": ["ticker", "as_of", "lane", "rank", "gates_passed"],
            "grader_hook": "scripts/grade_us_board.py (register us_standouts_v2.json "
                           "for a parallel track record; not yet present as of build)",
        },
    }


# --------------------------------------------------------------------------- #
#  render (unlinked preview page)                                              #
# --------------------------------------------------------------------------- #
def render(payload: dict, site=None) -> None:
    site = site or (config.ROOT / "site")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")),
                      autoescape=True)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = env.get_template("us_stocks_v2.html.j2").render(d=payload, built=built)
    write_page(site / "us_stocks_v2.html", html)
    log.info("wrote %s (%.0f KB)", site / "us_stocks_v2.html",
             (site / "us_stocks_v2.html").stat().st_size / 1024)


def build(write: bool = True, site=None) -> dict:
    site = site or (config.ROOT / "site")
    payload = compute(site)
    if write:
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / _OUT).write_text(
            json.dumps(payload, separators=(",", ":"), allow_nan=False))
        log.info("wrote %s (entry_open=%d setting_up=%d of %d candidates)",
                 _OUT, payload["counts"]["entry_open"],
                 payload["counts"]["setting_up"], payload["counts"]["candidates"])
        try:
            render(payload, site)
        except Exception as e:  # noqa: BLE001  a render hiccup must not fail the shadow
            log.warning("v2 preview render skipped (%s)", e)
    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s :: %(message)s")
    # SHADOW: swallow ALL failures. This runs after the live board; nothing it
    # does may break the render. Always return 0.
    try:
        build()
    except Exception as e:  # noqa: BLE001
        log.warning("v2 shadow build skipped (%s)", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
