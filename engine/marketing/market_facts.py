"""engine.marketing.market_facts — Deterministic fact sources for non-ticker content types.

Turns regime/daily_brief/heatmap/confluence artifacts into concrete, checkable
facts that macro/event/watchlist posts can weave in — same shape as chart_facts.py.

Public API:
    macro_facts(root)   -> {facts, numbers_whitelist}
    sector_facts(root)  -> {facts, numbers_whitelist}
    breadth_facts(root) -> {facts, numbers_whitelist}
    event_facts(root)   -> {facts, numbers_whitelist}

All functions:
- Return {"facts": [], "numbers_whitelist": []} on missing files (fail-soft)
- Are deterministic (no RNG, no network)
- Put every number that appears in a fact text into numbers_whitelist
- Never invent numbers — only values actually present in the source artifacts
- Use plain-word language, no indicator vocabulary (MACD/RSI/Stochastic/etc.)

Voice law (MARKETING_VOICE_DOCTRINE_V2 §6): fact TEXT feeds post copy, so it must
translate metrics into plain observable words. NO regime labels ("Goldilocks"), NO
internal scores (growth score / inflation score), NO "(read: ...)" asides, NO em
dashes. Say what the data plainly shows, e.g. "growth data keeps coming in soft while
inflation readings are still warm". If the facts are thin, say less.

DENOMINATOR LAW (Content Studio W1, 2026-07-29)
-----------------------------------------------
`research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md` §0 gate 3(f)
and §4 ("Jargon at the source"). **A count in a fact string carries its
denominator or it does not ship.** "18 groups on the move today" was generated
here, shipped on the flagship account, and is meaningless: 18 of how many? The
same fact class also carried a MISLABEL — `daily_brief.thematic_line.n_themes`
is the TOTAL number of themes the line tracks, not a count of movers, so
"on the move" was never true of it either.

Two structural rules now:
  1. Every count fact carries a machine-readable ``count`` block
     ``{"n_moving": int|None, "n_tracked": int|None, "noun": str}`` alongside
     its text. The writer translates FIELDS; it never has to parse a number
     back out of prose (masterplan §4).
  2. A count whose denominator is unknown is DROPPED, not phrased around. The
     supply-honest rule applies to facts as much as to volume: a numerator with
     no universe is not a fact, and no digit is better than a false one.

The module also stays clear of desk-machinery vocabulary in fact TEXT: no
screen, board, graded, plan, model, system, or "universe" (a word for our
ticker list, not for anything the reader can see). `tests/test_market_facts.py`
scans this module's string literals to keep it that way.

ANCHOR LAW (operator kill, 2026-08-01)
--------------------------------------
Three macro/event posts were pulled off the queue on the same morning:

    "4 of 11 sectors green on a day growth data firmed and inflation stayed
     warm. Not a clean enough read to lean on yet."
    "Not a clearcut tape. Growth firming a bit, inflation still warm, and only
     4 of 11 sectors managed green. I'm watching, not deciding."
    "growth data firmed a touch while inflation stayed warm. 4 of 11 sectors
     closed green. steady liquidity is the part i'm watching..."

The operator's verdict: "too bland, too weak, no real value, so esoteric no one
knows what it's talking about, zero engagement, people might even report us cuz
only bots/llm write garbage like this."

THE DEFECT IS IN THIS MODULE, NOT IN THE WRITER. Each of those posts is an
honest, in-register rendering of the fact packet it was handed, because the
packet's headline fact was a PRE-BAKED ABSTRACTION. ``_growth_words`` and
``_inflation_words`` turn ``growth_score`` / ``inflation_score`` into "growth
data firmed" and "inflation readings are still warm" — phrases that name no
release, carry no number, and cannot be checked, agreed with, or argued against.
A reader cannot picture "growth data". The denominator law fixed counts that
lacked a universe; this fixes claims that lack a PRINT.

WHAT REPLACES IT. ``data/regime/latest.json`` already carries the actual prints
behind those scores, each with its number and its publisher:

    conditions.labor_nowcast.initial_claims_4wk / claims_yoy_pct  (DOL claims)
    conditions.growth_nowcast.gdpnow                              (Atlanta Fed)
    conditions.inflation_nowcast.median_cpi                       (Cleveland Fed)
    conditions.inflation_nowcast.umich_1y_exp                     (UMich survey)
    liquidity_quality.stress_overlay.hy_oas_pct                   (HY spreads)
    conditions.style_tilt.yield_chg_1m_bp                         (10y, 1m)
    fed_path.policy_rate / fed_path.implied.m12                   (funds futures)
    yield_curve.shape.slope_2s10s.value                           (2s10s)

Those become :func:`named_print_facts`, and the highest-ranked one is FOLDED
into the growth/inflation read (macro) and the driver read (event) so the
packet's own top fact names a print. The abstraction is still allowed to carry
the STANCE ("growth data's firming up a little") — it just may no longer be the
whole claim.

NOTHING IS INVENTED. Every sentence below quotes a field that exists in the
artifact, with the units the producing engine documents (checked against
engine/conditions.py, engine/pit.py's FRED map, engine/yield_curve.py). A field
that is absent, unparseable or degenerate produces NO fact — the honest
degradation is a packet with one fewer anchor, and
``copywriter.anchorless_macro_violations`` then refuses the abstraction-only
post that would have been built from it.

UNITS ARE THE WHOLE GAME HERE, so the two traps found while writing this:
  * ``yield_curve.shape.level`` is the AVERAGE yield across the whole curve
    (engine/yield_curve.py: "parallel height"), NOT the 10-year. It is not used.
  * ``conditions.inflation_nowcast.sticky_ann`` did not read as an annual rate
    on the live artifact (0.23 where the series runs 2-6), so it is not used
    either. ``median_cpi`` is FRED MEDCPIM158SFRBCLE, published as percent
    change at an ANNUAL RATE, and is described as exactly that.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

_EMPTY: dict = {"facts": [], "numbers_whitelist": []}


def _growth_words(g: float) -> str:
    """Plain observable phrase for a growth score (no label, no number)."""
    if g <= -0.30:
        return "growth data keeps coming in soft"
    if g < -0.05:
        return "growth data's been running a touch soft"
    if g <= 0.05:
        return "growth data's been roughly steady"
    if g < 0.30:
        return "growth data's firming up a little"
    return "growth data's been running hot"


def _inflation_words(i: float) -> str:
    """Plain observable phrase for an inflation score (no label, no number)."""
    if i <= -0.30:
        return "inflation's cooling off fast"
    if i < -0.05:
        return "inflation's easing a little"
    if i <= 0.05:
        return "inflation's holding roughly flat"
    if i < 0.30:
        return "inflation readings are still a bit warm"
    return "inflation readings are still warm"


# Liquidity overlay → plain observable phrase (no label vocab)
_LIQUIDITY_PLAIN: dict[str, str] = {
    "expanding": "loosening",
    "contracting": "tightening up",
    "neutral": "roughly steady",
    "tightening": "tightening up",
    "easing": "loosening",
}


# ── Driver-label translation (market_drivers → plain speech) ─────────────────
# engine/market_drivers.py labels are dashboard shorthand ("hawkish repricing —
# cuts priced out, front-end up"). On the dashboard a legend and a chart carry
# the context; in a post the sentence is all the reader gets, so shorthand
# ships as gibberish — the 2026-07-27 flagship event post was these fragments
# verbatim. Every label the driver engine can emit gets a full sentence here
# with a subject and no desk vocabulary. A label with no entry is DROPPED, not
# sanitized: an untranslated driver read must never reach copy.
# tests/test_marketing_event_language.py fails if a driver is added to
# market_drivers.DRIVERS without a translation, so this table cannot fall
# behind silently.
_DRIVER_PLAIN: dict[str, str] = {
    "hawkish repricing — cuts priced out, front-end up":
        "Rates are doing the driving today. Traders are pricing out Fed cuts "
        "and short-term yields are climbing.",
    "dovish repricing — cuts priced in, front-end down":
        "Rates are doing the driving today. Traders are adding back Fed cut "
        "bets and short-term yields are falling.",
    "real yields rising — restrictive, gold & duration hit":
        "Real yields are pushing higher today. Gold and the big growth names "
        "are wearing it.",
    "real yields falling — easing, gold & duration bid":
        "Real yields are easing today. Gold and the big growth names are "
        "catching the bid.",
    "dollar surging — squeeze, commodities & em pressured":
        "The dollar is surging today, and it's squeezing commodities and "
        "emerging markets.",
    "dollar falling — risk tailwind, commodities & em bid":
        "The dollar is falling today, a tailwind for commodities and "
        "emerging markets.",
    "credit spreads widening — stress":
        "Credit is the story today. Spreads are widening, which is the bond "
        "market getting nervous.",
    "credit spreads compressing — risk-on":
        "Credit is setting the tone today. Spreads are tightening, which is "
        "the bond market giving risk a green light.",
    "net liquidity expanding — broad risk-on tailwind":
        "Liquidity is doing the lifting today. More money in the system, and "
        "risk assets are riding it.",
    "net liquidity draining — risk headwind":
        "Liquidity is the drag today. Money is draining out of the system "
        "and risk assets are fighting it.",
    "china risk-on — a-shares/hk & copper lead up":
        "China is leading today. Mainland and Hong Kong stocks are up and "
        "copper is moving with them.",
    "china risk-off — a-shares/hk & copper lead down":
        "China is the drag today. Mainland and Hong Kong stocks are down and "
        "copper is falling with them.",
    "oil spiking — energy leads, breakevens up":
        "Oil is the mover today. Energy names are leading and inflation "
        "expectations are creeping up with crude.",
    "oil collapsing — energy lags, breakevens down":
        "Oil is breaking down today. Energy names are lagging and inflation "
        "expectations are sliding with crude.",
    "ai/semis leadership — narrow tech-led tape":
        "AI and the chip names are carrying the tape today, and the "
        "leadership is narrow.",
    "ai/semis unwind — tech-led de-rating":
        "The AI and chip trade is unwinding today, with tech leading the "
        "selloff.",
    "crypto liquidity surging — btc/eth lead up":
        "Crypto is leading the risk appetite today. Bitcoin and ether are "
        "both bid.",
    "crypto liquidity draining — btc/eth lead down":
        "Crypto is leaking first today. Bitcoin and ether are both heavy.",
}

# Coherence flag → plain aside. The flag is INTERNAL machinery; the reader
# never hears "cross-checks" (the 2026-07-27 post did exactly that and read
# as a claim about nothing). Say what it means in tape terms instead.
_COHERENCE_PLAIN: dict[str, str] = {
    "supported": " The rest of the tape lines up with that.",
    "conflicted": " Not every market is on board with that read, though.",
    "mixed": " Not every market is on board with that read, though.",
    "unsupported": " The rest of the tape isn't really confirming it, though.",
}


def _plain_driver_read(direction: object) -> str | None:
    """Plain-English sentence for a market_drivers direction label.

    Returns None for an unknown label — callers must SKIP the fact, never
    ship the raw shorthand.
    """
    key = " ".join(str(direction or "").strip().lower().split())
    return _DRIVER_PLAIN.get(key)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: PathLike) -> dict | list | None:
    """Load JSON file; return None on any error."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _fmt_score(v: float) -> str:
    """Format a score as a signed float with 2 decimal places."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}"


def _fmt_pct(v: float, decimals: int = 1) -> str:
    """Format a signed percentage, e.g. '+2.1%'."""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%"


#: Saturation ceiling above which a count says nothing. ONE-SIDED on purpose —
#: see `_is_vacuous_count` for why the matching low arm was deleted.
#:
#: The high arm still mirrors ``content_studio._DEFAULT_DEGENERATE_BAND``'s upper
#: value BY VALUE, not by import: content_studio imports this module, so reading
#: the constant back out of it would be a cycle. The consumer-side gate stays the
#: second net; this is the first, and their SATURATION halves must agree or a
#: count the studio would drop still gets to be the digit a post is built around
#: before the studio ever sees it.
_VACUOUS_COUNT_MAX_RATIO: float = 0.95

#: Retained as a two-tuple for readers/tests that describe the gate's shape.
#: The low element is 0.0 because "no names qualified" is now the KNIFE-EDGE
#: case only (den==0 / num==0 are handled explicitly below), not a band.
_VACUOUS_COUNT_BAND: tuple[float, float] = (0.0, _VACUOUS_COUNT_MAX_RATIO)


def _is_vacuous_count(numerator: object, denominator: object) -> bool:
    """True when a count SATURATES its universe, or has no universe at all.

    A DENOMINATOR THE NUMERATOR CANNOT MOVE AGAINST IS NOT A DENOMINATOR
    (2026-07-28: four posts opened "231 of 231 names ... showing bullish
    momentum setups" and then argued "zero triggers" in the next sentence).

    WHAT THE DATA ACTUALLY CARRIES (investigated 2026-07-31 against the live
    site/factordata/tech_confluence.json): ``universe_n`` is 232 and IS the real
    scanned universe — the artifact carries no larger population to promote it
    to. The vacuity is on the NUMERATOR side: ``now`` is keyed by every one of
    those 232 names and counts a name as "active" if ANY of ~100 long combos is
    firing, which on every day observed is all 232. So the fact is structurally
    saturated and there is no denominator repair available; the only honest
    handling is to drop it.

    THE SATURATION GATE IS A BAND, NOT A STRICT INEQUALITY. ``n < universe`` is a
    knife-edge: 231 of 232 clears it and is exactly as vacuous as 232 of 232,
    and one name dropping off the screen was all it took to re-arm the sentence
    this rule exists to kill. So the high arm stays a ratio band.

    THE LOW ARM IS GONE, AND ITS DELETION IS THE POINT (2026-07-31). The gate was
    symmetric — ``ratio <= 0.05`` dropped anything under 5% of the universe — but
    the diagnosed defect was SATURATION ONLY. Symmetry was assumed, not measured,
    and it deleted the most newsworthy prints this lane can produce: "11 of 232
    names" is a washout, and a washout is INFORMATION. 231-of-232 says nothing
    because it cannot be otherwise; 11-of-232 says the screen almost emptied,
    which is rare, checkable, and exactly the kind of concrete fact the voice law
    asks for. A count near zero has a denominator it can move against in both
    directions — it is the opposite of degenerate.

    Two edges survive from the old low arm, and only these two:

      * ``den <= 0`` — no universe. There is nothing to be a fraction OF.
      * ``num <= 0`` — "0 of 232". This is the ONE genuinely empty print: it
        names no members, it reads identically on a day the screen ran and a day
        it silently returned nothing, and it is indistinguishable from the
        lane being broken. A washout has survivors; this has none.
    """
    try:
        num, den = float(numerator), float(denominator)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return True
    if den <= 0:
        return True  # no universe at all — the denominator law drops it anyway
    if num <= 0:
        return True  # "0 of N" — see the knife-edge note above
    return (num / den) >= _VACUOUS_COUNT_MAX_RATIO


def _count_block(n_moving: object, n_tracked: object, noun: str) -> dict:
    """The structured denominator a count fact carries (masterplan §4).

    ``n_moving`` is the numerator, ``n_tracked`` its universe, ``noun`` the
    plain word for what is being counted ("sectors", not "tiles"; "industry
    groups", not "themes"). Either number may be None — a caller with no
    denominator is expected to DROP the fact, and this block is what makes that
    decision inspectable rather than a comment.
    """
    def _int_or_none(v: object) -> int | None:
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    return {
        "n_moving": _int_or_none(n_moving),
        "n_tracked": _int_or_none(n_tracked),
        "noun": noun,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Named prints — the anchor a macro/event read is built on (see ANCHOR LAW)
# ─────────────────────────────────────────────────────────────────────────────

def _num(v: object) -> float | None:
    """Finite float or None. NaN and inf are absences, not values."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _dig(node: object, *path: str) -> object:
    """Walk a nested dict by key path; None the moment the path stops existing."""
    cur = node
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _pct1(v: float) -> str:
    """One-decimal unsigned percent.

    ONE decimal is not a style choice: ``copywriter.fake_precision_violations``
    rejects any percent carrying two, at every magnitude, so a "2.84%" written
    here would be minted by the packet and then refused by the validator that
    reads it — the gate-rejects-obedience failure this house has already paid
    for once.
    """
    return f"{v:.1f}%"


def _claims_level_words(lvl: float) -> tuple[str, str]:
    """(display phrase, whitelist token) for a claims level.

    "203 thousand", NOT "203,000". A comma-grouped integer is TWO tokens to
    ``copywriter._NUMBER_RE`` ("203" and "000"), so the whitelist would refuse
    the fact this module wrote — caught by
    ``test_market_facts.test_no_invented_numbers_in_macro_posts``, which is
    exactly the gate-rejects-obedience failure the number budget already cost
    this house once. "203k" is the natural X register but goes the other way:
    the whitelist tokenizer cannot see it AT ALL (no word boundary before the
    "k"), so an invented "213k" would sail through. A bare 3-6 digit integer is
    the one form the invention gate actually screens.

    The million arm is not hypothetical padding: the 4-week average of initial
    claims peaked near 5.8 MILLION in 2020, and the day this print matters most
    is the day "5800 thousand" would be the sentence.
    """
    if lvl >= 1_000_000:
        tok = f"{lvl / 1e6:.1f}"
        return f"{tok} million", tok
    tok = f"{int(round(lvl / 1000.0))}"
    return f"{tok} thousand", tok


def _print_jobless_claims(regime: dict) -> dict | None:
    """DOL weekly initial claims, 4-week moving average (FRED IC4WSA)."""
    lvl = _num(_dig(regime, "conditions", "labor_nowcast", "initial_claims_4wk"))
    if lvl is None or lvl <= 0:
        return None
    level_words, level_tok = _claims_level_words(lvl)
    yoy = _num(_dig(regime, "conditions", "labor_nowcast", "claims_yoy_pct"))
    if yoy is None or abs(yoy) < 0.05:
        return {
            "id": "print_jobless_claims",
            "text": f"Jobless claims are averaging {level_words} a week this month.",
            "numbers": [level_tok],
        }
    yoy_str = _pct1(abs(yoy))
    side = "below" if yoy < 0 else "above"
    return {
        "id": "print_jobless_claims",
        "text": (f"Jobless claims are averaging {level_words} a week this "
                 f"month, {yoy_str} {side} a year ago."),
        "numbers": [level_tok, yoy_str],
    }


def _print_gdpnow(regime: dict) -> dict | None:
    """Atlanta Fed GDPNow, the current-quarter real GDP nowcast (FRED GDPNOW)."""
    v = _num(_dig(regime, "conditions", "growth_nowcast", "gdpnow"))
    if v is None:
        return None
    s = _pct1(abs(v))
    verb = "growing" if v >= 0 else "shrinking"
    return {
        "id": "print_gdpnow",
        "text": (f"The Atlanta Fed's GDPNow has the economy {verb} at a {s} "
                 f"annual rate this quarter."),
        "numbers": [s],
    }


def _print_median_cpi(regime: dict) -> dict | None:
    """Cleveland Fed median CPI (FRED MEDCPIM158SFRBCLE), percent change at an
    annual rate — named as an annual rate because that is what it is."""
    v = _num(_dig(regime, "conditions", "inflation_nowcast", "median_cpi"))
    if v is None:
        return None
    s = _pct1(abs(v))
    # The series CAN print negative, and the month it does is the month this
    # post matters most. "running at a -1.2% annual rate" is the sentence a
    # signed format would have shipped on that day.
    verb = "falling" if v < 0 else "running"
    return {
        "id": "print_median_cpi",
        "text": f"The Cleveland Fed's median CPI is {verb} at a {s} annual rate.",
        "numbers": [s],
    }


def _print_umich_infl_exp(regime: dict) -> dict | None:
    """University of Michigan 1-year-ahead inflation expectations (FRED MICH)."""
    v = _num(_dig(regime, "conditions", "inflation_nowcast", "umich_1y_exp"))
    if v is None:
        return None
    s = _pct1(v)
    return {
        "id": "print_umich_infl_exp",
        "text": (f"The Michigan survey has households expecting {s} inflation "
                 f"a year out."),
        "numbers": [s],
    }


def _print_hy_spread(regime: dict) -> dict | None:
    """High-yield option-adjusted spread, in percent (engine/regime.py rounds to 2dp).

    Only the LEVEL carries a digit. ``hy_oas_chg_20d`` is itself rounded to one
    decimal in the artifact, so converting it to basis points would manufacture
    precision the source never had; the change ships as a direction word.
    """
    v = _num(_dig(regime, "liquidity_quality", "stress_overlay", "hy_oas_pct"))
    if v is None or v <= 0:
        return None
    s = _pct1(v)
    chg = _num(_dig(regime, "liquidity_quality", "stress_overlay", "hy_oas_chg_20d"))
    if chg is None or abs(chg) < 0.05:
        tail = " and roughly flat over the past month"
    elif chg > 0:
        tail = ", wider than a month ago"
    else:
        tail = ", tighter than a month ago"
    return {
        "id": "print_hy_spread",
        "text": f"High-yield credit spreads are at {s}{tail}.",
        "numbers": [s],
    }


def _print_10y_move(regime: dict) -> dict | None:
    """10-year Treasury yield change over ~1 month, in basis points.

    ``conditions.style_tilt.yield_chg_1m_bp`` is ``us10y.diff(21) * 100``
    (engine/conditions.py) — the 10-year specifically, not the curve average.
    """
    bp = _num(_dig(regime, "conditions", "style_tilt", "yield_chg_1m_bp"))
    if bp is None or abs(bp) < 1:
        return None
    n = f"{abs(bp):.0f}"
    direction = "up" if bp > 0 else "down"
    return {
        "id": "print_10y_move",
        "text": (f"The 10-year Treasury yield is {direction} {n} basis points "
                 f"over the past month."),
        "numbers": [n],
    }


def _print_fed_pricing(regime: dict) -> dict | None:
    """What fed funds futures price for the policy rate 12 months out.

    A market price, not a house view: ``fed_path.implied`` is built from ZQ
    futures (``implied_source_en``). The ``fed_stance`` LABEL beside it is
    display-only in the artifact and is deliberately not read here.
    """
    now = _num(_dig(regime, "fed_path", "policy_rate"))
    m12 = _num(_dig(regime, "fed_path", "implied", "m12"))
    if now is None or m12 is None or now <= 0 or m12 <= 0:
        return None
    now_s = _pct1(now)
    if abs(m12 - now) < 0.05:
        return {
            "id": "print_fed_pricing",
            "text": (f"Fed funds futures still put the policy rate at {now_s} "
                     f"a year out."),
            "numbers": [now_s],
        }
    m12_s = _pct1(m12)
    direction = "up" if m12 > now else "down"
    return {
        "id": "print_fed_pricing",
        "text": (f"Fed funds futures put the policy rate at {m12_s} a year "
                 f"out, {direction} from {now_s} today."),
        "numbers": [m12_s, now_s],
    }


def _print_curve_2s10s(regime: dict) -> dict | None:
    """The 2s10s Treasury spread, in basis points (yield_curve.shape, pp -> bp)."""
    v = _num(_dig(regime, "yield_curve", "shape", "slope_2s10s", "value"))
    if v is None:
        return None
    bp = int(round(v * 100))
    if bp == 0:
        return None
    n = f"{abs(bp)}"
    side = "above" if bp > 0 else "below"
    return {
        "id": "print_curve_2s10s",
        "text": f"The 10-year Treasury yield sits {n} basis points {side} the 2-year.",
        "numbers": [n],
    }


#: RANK ORDER, and it is the whole editorial judgement in this section: the
#: prints a general reader can picture and argue with come first (how many
#: people lost a job this week, how fast the economy is growing, what prices
#: are doing), the plumbing reads come last. Fixed rather than data-driven on
#: purpose — a rotation keyed on the day would make the packet non-reproducible
#: from the artifact alone, and the variant rotation that keeps posts from
#: repeating already lives one layer up (content_studio seeds it on `as_of`).
_NAMED_PRINT_BUILDERS: tuple = (
    _print_jobless_claims,
    _print_gdpnow,
    _print_median_cpi,
    _print_umich_infl_exp,
    _print_hy_spread,
    _print_10y_move,
    _print_fed_pricing,
    _print_curve_2s10s,
)

#: How many named prints one packet carries. THREE, because
#: ``copywriter.build_context`` hands the writer ``all_facts[:3]`` — a fourth
#: would never be seen by the writer but WOULD enter the numbers whitelist,
#: licensing a digit nobody showed it. The whitelist is the invented-number
#: gate; widening it for facts the prompt omits is how that gate goes soft.
_NAMED_PRINT_MAX = 3

#: Salience for the prints that ship STANDALONE. The top-ranked print is folded
#: into the packet's lead fact instead (see :func:`macro_facts`), which is what
#: guarantees the lead fact names a print; these two sit directly beneath it.
_NAMED_PRINT_SALIENCE: tuple[int, ...] = (11, 10)

#: Salience of a lead fact that has a print folded into it. Above every legacy
#: fact so the anchored read is one of the three the writer actually sees.
_ANCHORED_LEAD_SALIENCE = 12


def _named_prints(regime: object) -> list[dict]:
    """Ranked, de-duplicated named prints available from a regime artifact.

    Returns at most :data:`_NAMED_PRINT_MAX` entries, each
    ``{"id", "text", "numbers"}``. Empty when the artifact carries none — which
    is a real state (an empty root, a degraded build) and not an error.
    A builder that raises is skipped rather than allowed to take the packet
    down: one missing anchor costs a post its digit, a traceback costs the
    plan every non-ticker post it had.
    """
    if not isinstance(regime, dict):
        return []
    out: list[dict] = []
    for build in _NAMED_PRINT_BUILDERS:
        if len(out) >= _NAMED_PRINT_MAX:
            break
        try:
            p = build(regime)
        except Exception:  # noqa: BLE001
            p = None
        if p and p.get("text"):
            out.append(p)
    return out


def named_print_facts(root: PathLike) -> dict:
    """The named prints from ``data/regime/latest.json``, in the standard shape.

    Public because the anchor inventory is worth reading on its own (the admin
    Floor's supply view, tests, and any future lane that needs a checkable macro
    digit). ``macro_facts``/``event_facts`` fold and rank these themselves.
    """
    regime = _load_json(Path(root) / "data" / "regime" / "latest.json")
    prints = _named_prints(regime)
    facts = [
        {
            "id": p["id"],
            "text": p["text"],
            "salience": _ANCHORED_LEAD_SALIENCE - i,
            "numbers": list(p.get("numbers") or []),
        }
        for i, p in enumerate(prints)
    ]
    return _build(facts)


def _build(facts: list[dict]) -> dict:
    """Build the return shape from a list of fact dicts."""
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for f in facts:
        fid = f.get("id", "")
        if fid not in seen_ids:
            seen_ids.add(fid)
            deduped.append(f)

    seen_nums: set[str] = set()
    whitelist: list[str] = []
    for f in deduped:
        for num in f.get("numbers", []):
            if num and num not in seen_nums:
                seen_nums.add(num)
                whitelist.append(num)

    return {"facts": deduped, "numbers_whitelist": whitelist}


# ─────────────────────────────────────────────────────────────────────────────
# macro_facts
# ─────────────────────────────────────────────────────────────────────────────

def macro_facts(root: PathLike) -> dict:
    """Compute macro facts from regime/latest.json, site/neuralwebdata/daily_brief.json,
    and data/neuralweb/world_state.json.

    Example outputs (plain observable words, no labels or internal scores):
      "Growth data keeps coming in soft while inflation readings are still warm."
      "Liquidity's loosening a bit."
      "The picture's still shifting, not settled yet."
      "The AI and chip trade is unwinding today, with tech leading the selloff."
    """
    root = Path(root)
    regime_path = root / "data" / "regime" / "latest.json"
    brief_path = root / "site" / "neuralwebdata" / "daily_brief.json"

    regime = _load_json(regime_path)
    brief = _load_json(brief_path)

    if not regime and not brief:
        return dict(_EMPTY)

    facts: list[dict] = []

    # ── The ANCHOR: a named print with its number (operator kill 2026-08-01) ──
    # See the module docstring's ANCHOR LAW. The top-ranked print is FOLDED into
    # the growth/inflation read below rather than shipped beside it, because the
    # writer sees only the top three facts and the defect being fixed is that
    # the LEAD fact named nothing. Folding is what makes an anchorless macro
    # post hard to write; the remaining prints ship as siblings.
    _prints = _named_prints(regime)
    _anchor = _prints[0] if _prints else None
    _anchor_folded = False

    # ── The concrete digit a macro read carries (Content Studio W1) ───────────
    # WHAT USED TO BE HERE. `brief.thematic_line.n_themes` was folded into the
    # growth/inflation read as "{n} groups on the move today", for the stated
    # reason that "a macro post carries a concrete digit". It was two defects at
    # once:
    #   * NO DENOMINATOR. "18 groups on the move" is a numerator with no
    #     universe; the reader cannot tell whether that is broad or narrow.
    #     Masterplan §0 gate 3(f) names this exact string.
    #   * WRONG NOUN AND WRONG VERB. n_themes is the TOTAL count of themes the
    #     thematic line tracks (its own stage_counts sum to it), not a count of
    #     movers, and the themes are not "groups". The sentence was false, not
    #     merely thin.
    # WHAT REPLACES IT. The same fold-in mechanic over a fact that is actually
    # true: the sector board's green count over its universe. A real numerator,
    # a real denominator, a plain noun, and a reader can picture all three.
    # THE FOLD IS GATED ON THE COUNT BEING A READ, NOT A DEFINITION. The clause
    # asserts "closed green", so it may only be built from a numerator that
    # actually counts green sectors AND that says something: 0 of 11 and 11 of 11
    # are both true sentences and neither is a fact a reader learns anything
    # from, and reading a saturated block as "closed green" is how an all-red day
    # shipped as "11 of 11 sectors closed green today." A macro read with no
    # digit is the honest degradation; the module's own denominator law already
    # says a count that cannot be stated properly does not ship.
    _breadth_clause = ""
    _breadth_numbers: list[str] = []
    _breadth_count: dict | None = None
    for _sf in (sector_facts(root).get("facts") or []):
        if _sf.get("id") != "sector_leader":
            continue
        _cb = _sf.get("count") or {}
        _nm, _nt = _cb.get("n_moving"), _cb.get("n_tracked")
        if not isinstance(_nm, int) or not isinstance(_nt, int):
            break
        if _is_vacuous_count(_nm, _nt):
            break  # saturated either way: a definition, not a breadth read
        _breadth_clause = f"{_nm} of {_nt} sectors closed green today."
        _breadth_numbers = [str(_nm), str(_nt)]
        _breadth_count = dict(_cb)
        break

    # ── Growth + inflation, translated to plain observable words ──────────────
    # NO regime label, NO scores in the text. We read the underlying growth/
    # inflation scores and say what they plainly imply. The numbers stay internal.
    if isinstance(regime, dict):
        growth = regime.get("growth_score")
        inflation = regime.get("inflation_score")

        if growth is not None and inflation is not None:
            try:
                g = float(growth)
                infl = float(inflation)
                gw = _growth_words(g)
                iw = _inflation_words(infl)
                # Honest "not a comfortable mix" only when the two genuinely pull
                # opposite ways (soft growth + warm inflation, or vice versa).
                uncomfortable = (g < -0.05 and infl > 0.05) or (g > 0.05 and infl < -0.05)
                tail = " Not a comfortable mix." if uncomfortable else ""
                text = f"{gw[0].upper()}{gw[1:]} while {iw}.{tail}"
                _gi: dict = {
                    "id": "growth_inflation",
                    "text": text,
                    "salience": 10,
                    "numbers": [],
                }
                # ANCHOR FIRST, breadth second. Both are concrete, but only the
                # print answers the operator's actual complaint ("names no
                # print"): "4 of 11 sectors green" was IN the killed post and
                # did not save it, because a sector count is our arithmetic over
                # a board while a claims print is a release with a publisher and
                # a number a reader can look up. The breadth clause stays as the
                # fallback for the day the regime artifact carries no print at
                # all — a concrete observable beats an abstraction, which is
                # exactly what the pre-2026-08-01 fold was for.
                # PRINT FIRST, STANCE SECOND. The order is the fix, not a
                # cosmetic: the killed posts opened on the abstraction and a
                # reader bounced before reaching anything checkable. Lead with
                # the release and its number, then say what it means.
                if _anchor:
                    _gi["text"] = f"{_anchor['text']} {text}"
                    _gi["numbers"] = list(_anchor.get("numbers") or [])
                    _gi["salience"] = _ANCHORED_LEAD_SALIENCE
                    _anchor_folded = True
                elif _breadth_clause:
                    _gi["text"] = f"{text} {_breadth_clause}"
                    _gi["numbers"] = list(_breadth_numbers)
                    _gi["count"] = dict(_breadth_count or {})
                    _breadth_clause = ""  # folded; do not also ship it standalone
                facts.append(_gi)
            except (TypeError, ValueError):
                pass

        # ── Liquidity overlay ─────────────────────────────────────────────
        liq = regime.get("liquidity_overlay")
        if liq:
            liq_plain = _LIQUIDITY_PLAIN.get(str(liq).lower(), str(liq).lower())
            facts.append({
                "id": "liquidity_overlay",
                "text": f"Liquidity's {liq_plain} right now.",
                "salience": 7,
                "numbers": [],
            })

        # ── Transition state → plain words, no label ──────────────────────
        trans = str(regime.get("transition_state") or "").upper()
        if trans == "TRANSITIONING":
            facts.append({
                "id": "transition_state",
                "text": "The picture's still shifting, not settled yet.",
                "salience": 6,
                "numbers": [],
            })
        elif trans == "EARLY":
            facts.append({
                "id": "transition_state",
                "text": "Feels early in whatever this turns into.",
                "salience": 6,
                "numbers": [],
            })
        # STABLE (or anything else) → no separate fact; the growth/inflation line
        # already carries the read.

    # ── Daily brief narrative ─────────────────────────────────────────────────
    if isinstance(brief, dict):
        tape = brief.get("why_the_tape_moved") or {}
        if isinstance(tape, dict) and tape.get("available"):
            primary = tape.get("primary") or {}
            # Translated to a full plain sentence, or dropped. An unknown
            # driver label never ships as raw shorthand (2026-07-27 post).
            plain = _plain_driver_read(primary.get("direction"))
            if plain:
                facts.append({
                    "id": "tape_direction",
                    "text": plain,
                    "salience": 9,
                    "numbers": [],
                })

        # The standalone `theme_count` fact ("{n} different groups are on the
        # move today") is deleted for the same two reasons as the fold-in above:
        # no denominator, and n_themes is a total rather than a count of movers.

    # The breadth pair ships STANDALONE only when it was not folded into the
    # growth/inflation read above (i.e. no regime data). Never both: one fact
    # list must not say the same sentence twice.
    if _breadth_clause:
        facts.append({
            "id": "sector_breadth",
            "text": _breadth_clause[0].upper() + _breadth_clause[1:],
            "salience": 7,
            "numbers": list(_breadth_numbers),
            "count": dict(_breadth_count or {}),
        })

    # ── The named prints (ANCHOR LAW) ─────────────────────────────────────────
    # The top-ranked print ships standalone ONLY when the growth/inflation read
    # it was meant to anchor never got built (scores missing or unparseable).
    # Otherwise it lives inside that fact and saying it twice would burn a
    # writer-visible slot on a sentence already in the packet.
    _sibling_prints = _prints[1:] if _anchor_folded else _prints
    if _anchor and not _anchor_folded:
        facts.append({
            "id": _anchor["id"],
            "text": _anchor["text"],
            "salience": _ANCHORED_LEAD_SALIENCE,
            "numbers": list(_anchor.get("numbers") or []),
        })
        _sibling_prints = _prints[1:]
    for _i, _p in enumerate(_sibling_prints[:len(_NAMED_PRINT_SALIENCE)]):
        facts.append({
            "id": _p["id"],
            "text": _p["text"],
            "salience": _NAMED_PRINT_SALIENCE[_i],
            "numbers": list(_p.get("numbers") or []),
        })

    # Sort salience-DESC, id-ASC for determinism
    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# sector_facts
# ─────────────────────────────────────────────────────────────────────────────

def sector_facts(root: PathLike) -> dict:
    """Compute sector facts from site/marketdata/sp500_heatmap.json.

    Example outputs:
      "Energy led today +1.1%; only 1 of 11 sectors closed in the green."
      "Communication Services lagged today -1.3%."
      "ISRG fell -14.2% today, the biggest single-stock move in the index."
    """
    root = Path(root)
    hm_path = root / "site" / "marketdata" / "sp500_heatmap.json"
    hm = _load_json(hm_path)

    if not isinstance(hm, dict):
        return dict(_EMPTY)

    tiles = hm.get("tiles") or []
    if not isinstance(tiles, list) or not tiles:
        return dict(_EMPTY)

    # Aggregate sector performance (mean of 1D tile returns)
    from collections import defaultdict
    sector_vals: dict[str, list[float]] = defaultdict(list)
    best_stock_name = ""
    best_stock_pct = 0.0
    best_stock_abs = 0.0
    best_stock_ticker = ""

    for tile in tiles:
        if not isinstance(tile, dict):
            continue
        sector = tile.get("sector") or ""
        perf = tile.get("perf") or {}
        p1d = perf.get("1D")
        if sector and p1d is not None:
            try:
                sector_vals[sector].append(float(p1d))
            except (TypeError, ValueError):
                pass
        # Track biggest single-stock absolute mover
        if p1d is not None:
            try:
                abs_p = abs(float(p1d))
                if abs_p > best_stock_abs:
                    best_stock_abs = abs_p
                    best_stock_pct = float(p1d)
                    best_stock_ticker = tile.get("t") or ""
                    best_stock_name = tile.get("name") or best_stock_ticker
            except (TypeError, ValueError):
                pass

    if not sector_vals:
        return dict(_EMPTY)

    sector_avg = {
        s: sum(v) / len(v)
        for s, v in sector_vals.items()
    }
    sorted_sectors = sorted(sector_avg.items(), key=lambda x: x[1], reverse=True)

    facts: list[dict] = []

    # Best and worst sector
    if sorted_sectors:
        best_name, best_pct = sorted_sectors[0]
        worst_name, worst_pct = sorted_sectors[-1]

        # Count green sectors (positive mean return)
        n_green = sum(1 for _, v in sorted_sectors if v > 0)
        n_total = len(sorted_sectors)
        n_green_str = str(n_green)
        n_total_str = str(n_total)
        best_pct_str = _fmt_pct(best_pct)
        worst_pct_str = _fmt_pct(worst_pct)

        if best_pct > 0:
            text = (
                f"{best_name} led today {best_pct_str}; "
                f"{n_green_str} of {n_total_str} sectors closed in the green."
            )
            facts.append({
                "id": "sector_leader",
                "text": text,
                "salience": 8,
                "numbers": [best_pct_str, n_green_str, n_total_str],
                "count": _count_block(n_green, n_total, "sectors"),
            })
        else:
            # Broad red day. "All N" is its own denominator: numerator and
            # universe are the same number and the sentence says so.
            #
            # THE COUNT BLOCK STILL MEANS "HOW MANY CLOSED GREEN". This branch
            # used to publish `_count_block(n_total, n_total)` because the TEXT
            # says "all N", and macro_facts reads the block (not the text) to
            # build its breadth clause: the result was
            # "11 of 11 sectors closed green today." on a day when every sector
            # closed lower. One number, three defects (fabricated, inverted,
            # degenerate). The numerator is n_green, which on this branch is 0 by
            # construction (best_pct <= 0 means no sector's mean was positive),
            # and every consumer reads one meaning off the block.
            text = (
                f"All {n_total_str} sectors closed lower today; "
                f"{best_name} held up best at {best_pct_str}."
            )
            facts.append({
                "id": "sector_leader",
                "text": text,
                "salience": 8,
                "numbers": [n_total_str, best_pct_str],
                "count": _count_block(n_green, n_total, "sectors"),
            })

        if worst_name != best_name:
            text_worst = f"{worst_name} lagged today {worst_pct_str}."
            facts.append({
                "id": "sector_laggard",
                "text": text_worst,
                "salience": 7,
                "numbers": [worst_pct_str],
            })

    # Biggest single-stock mover
    if best_stock_ticker and best_stock_abs >= 3.0:
        direction = "rose" if best_stock_pct > 0 else "fell"
        pct_str = _fmt_pct(best_stock_pct)
        display = best_stock_name or best_stock_ticker
        text_stock = (
            f"{display} {direction} {pct_str} today, "
            f"the biggest single-stock move in the index."
        )
        facts.append({
            "id": "biggest_stock_mover",
            "text": text_stock,
            "salience": 6,
            "numbers": [pct_str],
        })

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# breadth_facts
# ─────────────────────────────────────────────────────────────────────────────

def breadth_facts(root: PathLike) -> dict:
    """Compute market-breadth/temperature facts from site/factordata/tech_confluence.json.

    Example outputs:
      "226 names in the S&P 500 universe are showing bullish momentum setups right now."
      "The most widely active setup across the index is a momentum-trend cluster."
    """
    root = Path(root)
    tc_path = root / "site" / "factordata" / "tech_confluence.json"
    tc = _load_json(tc_path)

    if not isinstance(tc, dict):
        return dict(_EMPTY)

    facts: list[dict] = []

    # ── Count tickers with any long combo firing ──────────────────────────────
    now = tc.get("now") or {}
    universe_n = tc.get("universe_n")

    # DENOMINATOR OR NOTHING (Content Studio W1, gate 3f). The two branches that
    # used to emit a bare "{n} names are showing bullish momentum setups" when
    # `universe_n` was missing or unparseable are deleted: that is a numerator
    # with no universe, which is the exact defect this wave closes. "S&P
    # universe" is gone too — "universe" is our word for our ticker list, not
    # something the reader can see.
    if isinstance(now, dict):
        n_active = len([t for t, v in now.items() if isinstance(v, list) and len(v) > 0])
        try:
            universe_int = int(universe_n) if universe_n else 0
        except (TypeError, ValueError):
            universe_int = 0
        # A DENOMINATOR THE NUMERATOR CANNOT MOVE AGAINST IS NOT A DENOMINATOR.
        # `now` is keyed by every tracked name and `universe_n` is the size of
        # that same list, so on a broad tape n_active == universe_n and the fact
        # reads "231 of 231 names we track are showing bullish momentum setups" —
        # denominated in form, vacuous in content, and the sentence a reader is
        # least able to argue with because it is a definition of the screen
        # rather than an observation about the market. Saturation drops the fact
        # here, at the producer, so it can never be the digit a macro or
        # watchlist post is built around; the configurable degenerate band in
        # content_studio.drop_degenerate_facts is the second net, not the first.
        # `_is_vacuous_count` (not `0 < n < universe`) because 231-of-232 is the
        # same non-fact as 231-of-231 — see that helper for the live artifact.
        if not _is_vacuous_count(n_active, universe_int):
            n_str = str(n_active)
            u_str = str(universe_int)
            text = (
                f"{n_str} of {u_str} names we track are showing bullish momentum "
                f"setups right now."
            )
            facts.append({
                "id": "breadth_active",
                "text": text,
                "salience": 8,
                "numbers": [n_str, u_str],
                "count": _count_block(n_active, universe_int, "names"),
            })

    # ── Most common setup — plain language, no indicator vocab ───────────────
    combos_block = tc.get("combos") or {}
    if isinstance(combos_block, dict):
        long_combos = combos_block.get("long") or []
    elif isinstance(combos_block, list):
        long_combos = combos_block
    else:
        long_combos = []

    if isinstance(now, dict) and long_combos:
        from collections import Counter
        combo_fires: Counter = Counter()
        for t, indices in now.items():
            if isinstance(indices, list):
                for i in indices:
                    if isinstance(i, int) and i < len(long_combos):
                        combo_fires[i] += 1

        _top_count_peek = combo_fires.most_common(1)[0][1] if combo_fires else 0
        if combo_fires and not _is_vacuous_count(_top_count_peek, universe_int):
            # Same law as breadth_active: the count ships with its universe or it
            # does not ship ("firing on 62 names" alone tells the reader nothing
            # about whether that is a lot), AND it does not ship saturated — a
            # setup firing on every name we track describes the screen, not the
            # tape. Band, not strict inequality: "firing on 230 of the 232 names
            # we track" is a screen definition wearing an observation's clothes.
            _top_idx, top_count = combo_fires.most_common(1)[0]
            top_count_str = str(top_count)
            u_str = str(universe_int)
            # Plain description — no indicator vocab, no combo id, no setup name.
            facts.append({
                "id": "top_setup_breadth",
                "text": (
                    f"The most active bullish setup is firing on {top_count_str} "
                    f"of the {u_str} names we track today."
                ),
                "salience": 6,
                "numbers": [top_count_str, u_str],
                "count": _count_block(top_count, universe_int, "names"),
            })

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# event_facts
# ─────────────────────────────────────────────────────────────────────────────

def event_facts(root: PathLike) -> dict:
    """Best-available event/catalyst fact for the day.

    Tries daily_brief first (why_the_tape_moved). Falls back to macro_facts —
    including when the driver label has no plain-English translation: a post
    built on macro context beats a post built on desk shorthand.

    Example output (a full sentence with a subject, no internal vocabulary):
      "The AI and chip trade is unwinding today, with tech leading the
       selloff. The rest of the tape lines up with that."
    """
    root = Path(root)
    brief_path = root / "site" / "neuralwebdata" / "daily_brief.json"
    brief = _load_json(brief_path)

    # ANCHOR LAW. The driver read says WHAT moved and in which direction; it
    # carries no number and several of its translations lean on exactly the
    # vocabulary the operator killed ("carrying the tape", "liquidity is doing
    # the lifting"). Folding a named print onto it is what turns "credit is the
    # story today" into a claim a reader can check.
    _prints = _named_prints(_load_json(root / "data" / "regime" / "latest.json"))

    facts: list[dict] = []

    if isinstance(brief, dict):
        tape = brief.get("why_the_tape_moved") or {}
        if isinstance(tape, dict) and tape.get("available"):
            primary = tape.get("primary") or {}
            coherence = str(primary.get("coherence") or "").lower()
            plain = _plain_driver_read(primary.get("direction"))
            if plain:
                _text = plain + _COHERENCE_PLAIN.get(coherence, "")
                _nums: list[str] = []
                _sal = 10
                if _prints:
                    _text = f"{_text} {_prints[0]['text']}"
                    _nums = list(_prints[0].get("numbers") or [])
                    _sal = _ANCHORED_LEAD_SALIENCE
                facts.append({
                    "id": "event_catalyst",
                    "text": _text,
                    "salience": _sal,
                    "numbers": _nums,
                })

    if not facts:
        # Fall back to macro facts as best available context. macro_facts runs
        # the same anchor fold, so the fallback is anchored too.
        return macro_facts(root)

    for _i, _p in enumerate(_prints[1:1 + len(_NAMED_PRINT_SALIENCE)]):
        facts.append({
            "id": _p["id"],
            "text": _p["text"],
            "salience": _NAMED_PRINT_SALIENCE[_i],
            "numbers": list(_p.get("numbers") or []),
        })

    facts.sort(key=lambda x: (-x["salience"], x["id"]))
    return _build(facts)


# ─────────────────────────────────────────────────────────────────────────────
# merge helper (for watchlist: combine breadth + sector)
# ─────────────────────────────────────────────────────────────────────────────

def merge_facts(*fact_dicts: dict) -> dict:
    """Merge multiple facts dicts, deduplicating by id, preserving order by salience."""
    combined: list[dict] = []
    seen_ids: set[str] = set()
    for fd in fact_dicts:
        if not isinstance(fd, dict):
            continue
        for f in fd.get("facts") or []:
            fid = f.get("id", "")
            if fid not in seen_ids:
                seen_ids.add(fid)
                combined.append(f)

    combined.sort(key=lambda x: (-x.get("salience", 0), x.get("id", "")))

    seen_nums: set[str] = set()
    whitelist: list[str] = []
    for f in combined:
        for num in f.get("numbers", []):
            if num and num not in seen_nums:
                seen_nums.add(num)
                whitelist.append(num)

    return {"facts": combined, "numbers_whitelist": whitelist}
