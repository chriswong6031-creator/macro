"""Fact-anchored consequences: the sentence that FOLLOWS from a chart fact.

WHY THIS MODULE EXISTS
======================
Every generated post is ``headline + {top_fact} + tail``. The fact sentence is
computed from real OHLCV by ``chart_facts.compute_facts`` and is good. The tail
was a **constant string baked into the template bank**, and that is where every
copy failure the operator rejected on 2026-07-28 lived:

    "$FDS | the group in one chart ... This is the name I read the whole
     space through."          → names no group anywhere (UNSUPPORTED CLAIM)
    "$ROST | on my desk all week ... One picture, whole thesis."
                              → says nothing (SAYS NOTHING)
    "That's most of why $FDS at 247.10 is worth your attention."
                              → the fact is its own justification (CIRCULAR)

The structural cause is one sentence long: **a fixed tail cannot follow from an
arbitrary fact.** Paste "One picture, whole thesis." under a 52-week high, a
volume spike, or a moving-average loss and it is equally true and equally
empty. That is the definition of filler.

So the tail stops being a constant and becomes a function of the fact's KIND.
``chart_facts`` already emits a typed ``id`` for every fact (``sma_50_reclaim``,
``new_52w_high``, ``avwap_reclaim``, ``nr7``, ...). Each kind has a real,
specific market-structure consequence, and this module is that mapping.

THE BAR (operator, 2026-07-28), which is also the acceptance test:
    a post must name a ticker, state a dated fact with its numbers, and then say
    something that FOLLOWS from that fact.

Every line here is written against the fact text it will sit behind, and every
line is *fact-anchored*: it refers back to the level, the price, the streak or
the mechanism the fact just established. That anchoring is what
``copywriter.consequence_violations`` screens for, so a future line added here
without an anchor fails the bank walk in tests/test_marketing_copy_substance.py
rather than shipping.

HOUSE CONSTRAINTS baked into every line below:
  - no em/en dashes (``banned_language``)
  - no study names: "VWAP"/"AVWAP"/"POC"/"point of control"/"value area" are
    banned vocab, so the anchored-price and volume-profile consequences use the
    same plain wording the facts themselves use ("the average price paid since
    the ... volume spike", "the most-traded price")
  - <= _MAX_CONSEQUENCE_CHARS so headline + fact + consequence + stance clears
    the 275-char post budget
  - a stance is NOT a consequence. "Watching, not buying" is a fine thing to say
    AFTER a consequence and is not one by itself.
"""

from __future__ import annotations

import hashlib
import re

# A consequence must leave room for headline + fact + a short stance inside the
# 275-char post budget. Enforced over the whole bank by the substance suite.
_MAX_CONSEQUENCE_CHARS = 128


# ─────────────────────────────────────────────────────────────────────────────
# Fact-id normalisation
#
# chart_facts emits period/window-parameterised ids (sma_20_reclaim,
# sma_50_reclaim, sma_200_loss, pct_5d, pct_20d). The consequence of reclaiming
# an average does not change with the period, so those collapse to one key. The
# period itself is already named in the fact text ("its 50-day average").
# ─────────────────────────────────────────────────────────────────────────────

_SMA_RECLAIM_RE = re.compile(r"^sma_\d+_reclaim$")
_SMA_LOSS_RE = re.compile(r"^sma_\d+_loss$")
_PCT_RE = re.compile(r"^pct_\w+$")


def normalize_fact_id(fact_id: str) -> str:
    """Collapse parameterised fact ids onto their consequence key."""
    fid = (fact_id or "").strip()
    if _SMA_RECLAIM_RE.match(fid):
        return "sma_reclaim"
    if _SMA_LOSS_RE.match(fid):
        return "sma_loss"
    if _PCT_RE.match(fid):
        return "pct_change"
    return fid


# ─────────────────────────────────────────────────────────────────────────────
# The bank. Keyed by normalised fact id; every value is a list of interchangeable
# consequences for that fact kind.
#
# Multiple variants per kind is not decoration: two posts on one account that
# share a fact kind AND a consequence produce near-identical SKELETONS (the copy
# with tickers and numbers blanked), which is exactly what sentinel's frame gate
# drops. Variants are what let an account run two moving-average reclaims in a
# day without one of them being killed as a repeated frame.
# ─────────────────────────────────────────────────────────────────────────────

CONSEQUENCES: dict[str, list[str]] = {

    # ── moving averages ──────────────────────────────────────────────────────
    # Fact: "TEL reclaimed its 50-day average (205.23), first time since Jul 2026"
    "sma_reclaim": [
        "One reclaim isn't a trend. It has to hold that level on a pullback before it's a setup.",
        "The average that capped it is now the level that has to support it. That's the test.",
        "A first close back above after that long is a change of state, not an entry. The retest is the entry.",
        "Everyone who sold into that average now has to decide whether to buy it back higher.",
    ],
    # Fact: "TEL lost its 50-day average (205.23), first time since Jul 2026"
    "sma_loss": [
        "That average is overhead now. Rallies back into it are where the sellers have been waiting.",
        "Losing it after that long is the first real crack. Whether it closes back above quickly is the tell.",
        "The buyers who defended that level stopped showing up. Until they're back, strength is supply.",
    ],

    # ── 52-week extremes ─────────────────────────────────────────────────────
    # Fact: "ROST hit a new 52-week high"
    "new_52w_high": [
        "Nobody who owns it is underwater, so there's no trapped supply to sell into strength.",
        "New highs are where I stop guessing and start watching the retest. The old high is what it defends.",
        "Every seller from the last year is already out. What's left is profit-taking, not rescue selling.",
    ],
    # Fact: "ROST hit a new 52-week low"
    "new_52w_low": [
        "Everyone who bought in the last year is underwater, so every rally has sellers inside it.",
        "There's no reference price left underneath. The low itself becomes the only thing to lean on.",
        "Nobody is trapped short here. All the overhead is long, and that's what caps the bounce.",
    ],
    # Fact: "FDS is 2.4% below its 52-week high (272.40)"
    "near_52w_high": [
        "That's close enough that the high is the level. Clear it and there's no overhead supply left.",
        "Fail here and it's a second rejection from the same place, which is how ranges get built.",
        "One level stands between it and open air. Everything from here depends on that one number.",
    ],
    # Fact: "FDS is 3.1% above its 52-week low (198.10)"
    "near_52w_low": [
        "Holding above the low is the whole argument. Below it the chart has no reference left.",
        "This close to the low, the low is the trade. It either holds and bounces or it doesn't.",
    ],

    # ── volume ───────────────────────────────────────────────────────────────
    # Fact: "CBOE had its highest daily volume in ~14m today"
    "volume_record": [
        "Volume that size is a mandate, not drift. Whoever needed that many shares rarely finishes in a session.",
        "Price can be talked up, that much volume can't. Something changed hands for a reason.",
        "The heaviest session in over a year is repositioning, not the usual buyers rotating.",
    ],
    # Fact: "CBOE saw 3.2x its average volume today"
    "volume_surge": [
        "Volume that far above normal is someone with size. The follow-through session says whether they're done.",
        "That's more shares than the usual holders own between them. New money set the price today.",
        "Moves on normal volume fade. Moves on multiples of it tend to get defended.",
    ],

    # ── streaks ──────────────────────────────────────────────────────────────
    # Fact: "LKFN has closed green 5 sessions in a row"
    "streak_green": [
        "Streaks that long are usually late. I'd rather have the first pullback than the sixth green close.",
        "The buying is real, but so is the distance back to anywhere sensible to stop.",
    ],
    # Fact: "LKFN has closed red 5 sessions in a row"
    "streak_red": [
        "Selling that persistent is either capitulation or information. The first green close tells you which.",
        "Every dip buyer so far has been wrong. That's what makes the next real bounce worth having.",
    ],
    # Fact: "LKFN has been up 4 weeks in a row"
    "weekly_streak_up": [
        "Four weeks without a down week is a trend doing its job. The first weekly loss is the news.",
        "On the weekly frame that's persistence, not noise. It gets interesting when it stops.",
    ],
    # Fact: "LKFN has been down 4 weeks in a row"
    "weekly_streak_dn": [
        "A month of lower weekly closes isn't a dip. The first up week is the earliest thing worth acting on.",
        "Weekly downtrends end with a week that refuses to close red. That hasn't happened yet.",
    ],

    # ── single-session events ────────────────────────────────────────────────
    # Fact: "CUBI moved +8.2% today, its biggest single-day up in ~14m"
    "biggest_move": [
        "A move that size repriced the whole thing in a session. The follow-through day matters more than the move.",
        "Days like this either get given back within the week or they hold and become the new base.",
    ],
    # Fact: "CUBI is in a tight range today, narrowest of the last 7 sessions (range: 2.14)"
    "nr7": [
        "Ranges that tight resolve. The direction of the break is the trade, not the range itself.",
        "Compression like that is the market running out of disagreement. Something gives shortly.",
    ],

    # ── anchored average price (study name is banned: plain wording only) ────
    # Fact: "CUBI closed back above 77.99, the average price paid since the Jun 26 volume spike"
    "avwap_reclaim": [
        "Everyone who bought that spike is roughly flat instead of underwater, which changes who sells into strength.",
        "That price is where the spike buyers stop feeling trapped. It matters more than any round number.",
        "Back above what the last wave of buyers paid, the pressure to sell every bounce comes off.",
    ],
    # Fact: "CUBI has held 77.99, the average price paid since the Jun 26 volume spike, for 22 straight sessions"
    "avwap_hold": [
        "Weeks of closes above what those buyers paid is a floor with real money behind it, not a drawn line.",
        "They've had every chance to get out flat and haven't. That level is being defended on purpose.",
    ],

    # ── volume distribution (study names banned: plain wording only) ─────────
    # Fact: "FDS is 1.8% above 205.23, the price where the most shares changed hands in the past 3 months"
    "poc_level": [
        "That's where the most shares changed hands, so it's where the most opinions have to be revised.",
        "Above the busiest price, the people who bought there stop being sellers and start being holders.",
    ],
    # Fact: "FDS is sitting between 200.00 and 210.00, where most of the past 3 months of volume traded"
    "in_value_area": [
        "Inside the heaviest volume there's no edge. Both sides think they're right and it goes nowhere.",
        "This is the crowded pocket. The trade sits at the edges of that band, not in the middle of it.",
    ],
    # Fact: "FDS dipped back to 205.23, the most-traded price of the past 3 months, and held"
    "poc_retest_hold": [
        "It went back to where the most shares changed hands and the buyers were still there. Test passed.",
        "A retest that holds turns the busiest price on the chart from resistance into support.",
    ],

    # ── publish-time movers (engine/marketing/movers_source.mover_facts) ────
    # Fact: "TEL surged +8.2% today (Technology)."
    "mover_pct": [
        "A move that size in one session repriced it. The follow-through day matters more than the move.",
        "Day one after a move like this is information, not an entry. The setup comes later or not at all.",
        "Moves this big either get given back within the week or they hold and become the new base.",
    ],
    # Fact: "TEL is 8.2% lower on the day, one of the biggest moves in the index."
    "mover_magnitude": [
        "Everyone who bought in the last few weeks is underwater, and that supply sits over every bounce.",
        "Drops this size don't finish in a session. The low that holds on the retest is the one to mark.",
    ],

    # ── market-wide facts (engine/marketing/market_facts) ───────────────────
    # These feed the macro / event / education banks, which carry no ticker and
    # no chart. On 2026-07-28 nine of them opened with the byte-identical
    # sentence because growth_inflation sits at salience 10 and always wins the
    # lead slot, and every tail behind it was pure commentary. The fact is fine;
    # what follows it now has to be about the fact.
    #
    # Every line here is polarity-neutral by construction: the fact supplies the
    # direction ("steady growth / warm inflation", "7 of 11 sectors green"), the
    # consequence supplies what that shape implies either way. A line that only
    # reads correctly for one direction would ship as a false statement on the
    # other, which is the same defect class in a new outfit.

    # Fact: "Growth data's been roughly steady while inflation readings are
    #        still warm. 18 groups on the move today."
    "growth_inflation": [
        "Broad moves mean the tape agrees. Narrow ones mean a few names are carrying it, and that's a different market.",
        "Growth and inflation pulling different ways is what keeps money rotating between groups instead of committing.",
        "Nothing about that mix resolves until one of the two readings changes. Until then, rotation is the default.",
    ],
    # Fact: "Liquidity's tight right now."
    "liquidity_overlay": [
        "Liquidity decides how far a given amount of buying moves price. Same news in a different week lands differently.",
        "Tight or loose, it sets how much price moves per dollar of buying. Everything else is downstream of that.",
    ],
    # Fact: "The picture's still shifting, not settled yet."
    "transition_state": [
        "Unsettled means the levels that worked last month are the ones most likely to fail. Smaller size until it settles.",
        "Both the old read and the new one look right in here, which is how positions get too big at the worst moment.",
    ],
    # Fact: plain read of what moved the tape today.
    "tape_direction": [
        "What moved the tape matters more than where it closed. The driver is the part that repeats.",
        "Direction with a reason behind it holds better than direction without one.",
    ],
    # Fact: "18 different groups are on the move today."
    "theme_count": [
        "That count is the breadth check. Wide is a market moving, narrow is a few names and a headline.",
        "The more groups involved, the less any single name's move is telling you about that name.",
    ],
    # Fact: "Energy led today +2.1%; 7 of 11 sectors closed in the green."
    "sector_leader": [
        "How many sectors joined in is the tell. One green sector is a story, most of them is a market.",
        "Leadership only matters if it repeats. One session at the top is noise until the second one.",
    ],
    # Fact: "Utilities lagged today -1.4%."
    "sector_laggard": [
        "The laggard is where the forced selling shows up first. Worth knowing before it's obvious.",
        "Something has to be last. Whether it lags again tomorrow is what separates a bad day from a broken trend.",
    ],
    # Fact: "NVDA rose +8.2% today, the biggest single-stock move in the index."
    "biggest_stock_mover": [
        "One name moving that far pulls the index with it, which flatters or hides what everything else did.",
        "The biggest mover sets the headline. What the other names did underneath it is the actual read.",
    ],
    # Fact: "142 of 503 names in the S&P universe are showing bullish momentum
    #        setups right now."
    "breadth_active": [
        "That share is the breadth number I care about. Rising counts precede trends, falling ones precede stalls.",
        "How many names qualify at once tells you whether to press or to sit. Nothing else about the day does.",
    ],
    # Fact: "The most active bullish setup is firing on 31 names today."
    "top_setup_breadth": [
        "One setup firing on that many names at once is a market condition, not a coincidence.",
        "A crowded setup cuts both ways: more chances to be right, and more people positioned the same way.",
    ],
    # Fact: plain read of the event and how cleanly the tape agreed with it.
    "event_catalyst": [
        "Markets move on surprise, not news. How much of that was actually a surprise is the question worth asking.",
        "The first reaction and the one that sticks are usually different. The close is the one that counts.",
    ],

    # ── plain percentage change ─────────────────────────────────────────────
    # Fact: "TEL is up 12.3% over the last month"
    "pct_change": [
        "A move that size is already priced. Whether it can hold the gain matters more than extending it.",
        "That's a lot of ground in a short window. The pullback that doesn't give it all back is the tell.",
    ],
}


def has_consequence(fact_id: str) -> bool:
    """True when this fact kind has a consequence bank entry."""
    return normalize_fact_id(fact_id) in CONSEQUENCES


def consequence_for(
    fact_id: str,
    *,
    seed: str = "",
) -> str:
    """The sentence that follows from a fact of this kind. "" when unknown.

    Deterministic in ``seed`` (caller passes ticker|account|slot), so the same
    post regenerates identically while two different tickers on one account
    land on different variants. That spread is what keeps sentinel's per-account
    frame gate from having to drop one of them as a repeated skeleton.
    """
    key = normalize_fact_id(fact_id)
    variants = CONSEQUENCES.get(key)
    if not variants:
        return ""
    if not seed:
        return variants[0]
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return variants[h % len(variants)]


def consequence_from_facts(
    top_facts: list[dict],
    *,
    seed: str = "",
) -> str:
    """Consequence for the highest-salience fact that has one. "" when none do.

    ``top_facts`` arrives salience-ordered from build_context, so this walks in
    priority order and takes the first fact kind the bank covers. A post whose
    every fact is uncovered gets "", which renders the {consequence} token empty
    and leaves the copy to fail the substance screen rather than ship filler.
    """
    for fact in top_facts or []:
        if not isinstance(fact, dict):
            continue
        text = consequence_for(str(fact.get("id") or ""), seed=seed)
        if text:
            return text
    return ""
