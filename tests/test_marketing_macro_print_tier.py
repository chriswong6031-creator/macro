"""Release importance decides the desk — a minor print leaves the brand account.

THE DEFECT (operator, 2026-08-05, reading the live @mastermindx001 timeline):
"These posts are so boring, we get absolutely no engagement on them. I think it
will hurt our accounts by posting these really boring economic releases... These
arent the ones people really care about."

Measured from the committed outbox, the SEVEN `kind="breaking"` items the
flagship shipped after the 2026-08-03 clustering fix merged (14:39Z) — i.e. the
live behaviour, with every earlier burst excluded:

    South Korea core inflation           JOLTS job openings
    US non-farm payrolls lookahead       Canada June trade balance
    "Unite Secures Inflation-Beating     investingLive Asia-Pacific FX wrap
     10.5% Pay Package ... GXO Drivers"  USA Trade Balance For June

Not one is a top-tier US release. THE CAUSE IS NOT VOLUME AND NOT DEDUP — the
per-account ceilings were removed by operator order on 2026-08-04, and no
repeat-event burst has shipped since the clustering fix. It is SELECTION:
`breaking_relevance._MACRO_PRINT_KEYWORDS` is a flat list, so every macro print
scores the same base 55.0, and `wire_routing.classes.macro_print: flagship` then
addressed all of them to the brand account. `test_the_flat_list_defect_is_the
_whole_story` pins that equality directly.

BOTH DIMENSIONS BIND. Tier alone leaves GERMANY RETAIL SALES (a tier-1 TOPIC) on
the flagship; economy alone leaves JOLTS and the US trade balance there. The
tests below fail on the pre-2026-08-05 code, where every case returned
"flagship".
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.marketing import breaking_relevance as BR
from engine.marketing import wire_routing as WR

#: Routing reads the outbox for its volume ceiling, and `route` defaults to the
#: repo root — a rootless call here would read the COMMITTED queue and quietly
#: turn a routing assertion into a statement about whatever the wire posted
#: today. Every call below passes this empty root.
EMPTY = Path(tempfile.mkdtemp(prefix="macro-tier-empty-"))

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _reset():
    WR.reset_dark_route_warnings()
    WR.reset_volume_cache()
    yield
    WR.reset_dark_route_warnings()
    WR.reset_volume_cache()


def _cfg(*, minor_row: str | None = "mastermind_news") -> dict:
    """marketing.yml-shaped: both desks live, the refined row switchable.

    `minor_row=None` OMITS `macro_print.minor` entirely — the pre-2026-08-05
    config, used to pin that deleting the row restores the old behaviour.
    """
    classes = {"macro_print": "flagship",
               "policy": "flagship",
               "geopolitical": "mastermind_news",
               "company_news": "mastermind_news"}
    if minor_row is not None:
        classes["macro_print.minor"] = minor_row
    return {
        "desk_network": {"accounts": [{"id": "flagship", "enabled": True},
                                      {"id": "mastermind_news", "enabled": True}]},
        "wire_routing": {"default": "flagship", "classes": classes},
    }


def _desk(headline: str, *, snippet: str = "", cfg: dict | None = None) -> str:
    """Score a headline the way the press lane does, then route it.

    Goes through `score_item` rather than calling the tier function directly:
    the seam under test is the whole path (classify -> tier -> refine -> route),
    and a test that stubbed the middle would pass with the refinement never
    reaching `route`.
    """
    scored = BR.score_item({"headline": headline, "body_snippet": snippet,
                            "source_tier": "wire"},
                           now=NOW, universe=frozenset(), root=EMPTY)
    tier = str(scored.get("macro_tier") or "")
    economy = str(scored.get("macro_economy") or "")
    refinement = "" if not tier else (
        "" if (tier == "tier1" and economy == "us") else "minor")
    return WR.route(scored.get("event_class", "none"),
                    cfg=cfg or _cfg(), root=EMPTY, refinement=refinement)


# ─────────────────────────────────────────────────────────────────────────────
# The live timeline: what the operator actually saw
# ─────────────────────────────────────────────────────────────────────────────

#: Verbatim from `data/marketing/outbox/items.jsonl` — the flagship's breaking
#: posts after the clustering fix merged. The GXO line is the one that shows the
#: taxonomy is matching a WORD and not a release: it is a UK trucking-union pay
#: settlement that classified `macro_print` off the bare token "inflation".
OPERATOR_SAW_MINOR = [
    "More info on this - South Korea core inflation hits 2-1/2 year high despite headline cooling",
    "Unite Secures Inflation-Beating 10.5% Pay Package Increase For GXO Drivers In Bellshill, Backdated",
    "JOLTs job openings 7.359M vs 7.400M estimate. Lower than last month.",
    "Canada June trade balance +3.86B vs +3.0B expected",
    "USA Trade Balance For June -73.30B Vs -73.00B Est.",
    "SWITZERLAND (JUL) CPI CORE YOY ACTUAL: 0.3% VS 0.3% PREVIOUS;EST 0.3%",
    "GERMANY (JUN) RETAIL SALES MOM ACTUAL: -1.1% VS 1.1% PREVIOUS;EST -0.3%",
]


@pytest.mark.parametrize("headline", OPERATOR_SAW_MINOR)
def test_the_posts_the_operator_complained_about_leave_the_flagship(headline):
    """Every one of these returned "flagship" before this change."""
    assert _desk(headline) == "mastermind_news", headline


# ─────────────────────────────────────────────────────────────────────────────
# The releases we KEEP — the fix must not silence the lane
# ─────────────────────────────────────────────────────────────────────────────

TAPE_MOVERS = [
    "US CPI rises 0.3% m/m in July versus 0.2% estimate",
    "US non-farm payrolls +180k vs +150k estimate; unemployment rate 4.1%",
    "Core PCE price index +0.2% m/m, in line with estimates",
    "Real GDP grew at an annual rate of 1.5 percent in the second quarter",
    "Retail sales +0.5% vs +0.3% expected",
    "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate",
    "PPI final demand +0.1% m/m vs +0.2% estimate",
    "Initial jobless claims 221k vs 230k expected",
    "FOMC holds the fed funds target range at 4.25-4.50%",
]


@pytest.mark.parametrize("headline", TAPE_MOVERS)
def test_tape_moving_us_releases_stay_on_the_flagship(headline):
    """The ratified keep-list. A selection fix that silences the lane is a bug."""
    assert _desk(headline) == "flagship", headline


def test_a_us_payrolls_lookahead_stays_because_it_is_about_a_tape_mover():
    """The 7th live post, kept DELIBERATELY — recorded so the choice is visible.

    "The US non-farm payrolls report is due this week" is a lookahead, not a
    print. It stays on the flagship because the ratified rule is about which
    RELEASE a post concerns, and this one concerns the release the whole tape is
    positioned for. It is also the one post in the live seven the operator did
    not screenshot. Change this test, not the code, if that judgment is revised.
    """
    assert _desk("The US non-farm payrolls report is due this week, with July "
                 "headline estimates at +80k versus June's print") == "flagship"


# ─────────────────────────────────────────────────────────────────────────────
# The defect itself
# ─────────────────────────────────────────────────────────────────────────────

def test_the_flat_list_defect_is_the_whole_story():
    """Identical salience, different desks — the fix is routing, not scoring.

    Pins the measured equality the change is built on: the taxonomy cannot tell
    a Swiss CPI sub-print from a US CPI print, and this change does not teach it
    to. Anyone "fixing" this by demoting minor prints in the SCORE breaks this
    test, which is the point — a salience demotion would also drop them below
    the emit threshold and delete the record instead of relaying it.
    """
    swiss = BR.score_item(
        {"headline": "SWITZERLAND (JUL) CPI CORE YOY ACTUAL: 0.3%",
         "source_tier": "wire"}, now=NOW, universe=frozenset(), root=EMPTY)
    us = BR.score_item(
        {"headline": "US CPI rises 0.3% m/m in July", "source_tier": "wire"},
        now=NOW, universe=frozenset(), root=EMPTY)

    assert swiss["event_class"] == us["event_class"] == "macro_print"
    assert swiss["salience"] == us["salience"]        # the flat list, measured
    assert swiss["macro_tier"] == us["macro_tier"] == "tier1"   # same RELEASE
    assert (swiss["macro_economy"], us["macro_economy"]) == ("foreign", "us")
    assert _desk("SWITZERLAND (JUL) CPI CORE YOY ACTUAL: 0.3%") == "mastermind_news"
    assert _desk("US CPI rises 0.3% m/m in July") == "flagship"


def test_both_dimensions_bind_neither_alone_is_enough():
    """Either half alone still ships the operator's complaint."""
    # Tier-1 TOPIC, foreign economy — tier alone would keep this on the brand.
    german = BR.macro_print_tier(
        "macro_print", "germany (jun) retail sales mom actual: -1.1%")
    assert german[:2] == ("tier1", "foreign")

    # US economy, tier-2 release — economy alone would keep this on the brand.
    trade = BR.macro_print_tier(
        "macro_print", "usa trade balance for june -73.30b vs -73.00b est.")
    assert trade[:2] == ("tier2", "us")


def test_the_bare_word_inflation_is_not_a_tier_one_release():
    """The token that put a UK trucking-union pay deal on the brand account.

    A real CPI or PCE print names itself; "inflation" appears in wage stories,
    corporate commentary and politics. It stays in the CLASS vocabulary (the
    item is still a macro print) and is deliberately absent from the tier-1 one.
    """
    tier, _, release = BR.macro_print_tier(
        "macro_print",
        "unite secures inflation-beating 10.5% pay package increase for gxo "
        "drivers in bellshill, backdated")
    assert (tier, release) == ("tier2", "")


def test_an_explicit_us_marker_outranks_a_named_foreign_economy():
    """"US trade deficit with China" is a US print that happens to name China."""
    assert BR.macro_print_tier(
        "macro_print", "u.s. trade deficit with china widens in june")[1] == "us"


def test_an_unmarked_print_reads_as_us():
    """Our feeds are US-centric; a BLS headline routinely names no country."""
    assert BR.macro_print_tier("macro_print", "retail sales +0.5% vs +0.3% est")[1] == "us"


# ─────────────────────────────────────────────────────────────────────────────
# Blast radius: this may not touch anything but macro_print routing
# ─────────────────────────────────────────────────────────────────────────────

def test_the_tier_has_no_opinion_about_other_classes():
    """Scoped like `macro_revision_penalty` — a future class cannot inherit it."""
    for klass in ("policy", "geopolitical", "company_news", "none", ""):
        assert BR.macro_print_tier(klass, "switzerland cpi core yoy 0.3%") == ("", "", "")


@pytest.mark.parametrize("headline,klass,desk", [
    ("Israel and Hamas agree ceasefire terms after talks",
     "geopolitical", "mastermind_news"),
    ("Merck raises revenue guidance as new drug sales grow",
     "company_news", "mastermind_news"),
    ("Trump announces new 25% tariffs on imported steel",
     "policy", "flagship"),
])
def test_other_classes_route_exactly_as_before(headline, klass, desk):
    """A refinement narrows ONE class; every other row is untouched.

    Asserts the CLASS as well as the desk. A headline that quietly stopped
    classifying would otherwise route to the config default and pass this test
    for entirely the wrong reason.
    """
    scored = BR.score_item({"headline": headline, "source_tier": "wire"},
                           now=NOW, universe=frozenset(), root=EMPTY)
    assert scored["event_class"] == klass, headline
    assert scored["macro_tier"] == ""          # no refinement is derivable
    assert _desk(headline) == desk, headline


def test_deleting_the_refined_row_restores_the_old_behaviour():
    """The bare `macro_print` row is the fallback — pins the config's own claim.

    A refinement may only move an item off the desk its class names. It can
    never address an item to a desk no row mentions, so a config that predates
    this change routes exactly as it did.
    """
    old = _cfg(minor_row=None)
    for headline in OPERATOR_SAW_MINOR:
        assert _desk(headline, cfg=old) == "flagship", headline


def test_an_item_scored_before_the_tier_existed_routes_by_class():
    """No `macro_tier` stamp -> no refinement -> the class owns it.

    press_lane reads the stamp rather than re-deriving it, so an item queued by
    an older process must not crash or silently change desks.
    """
    from engine.marketing.press_lane import _macro_refinement

    assert _macro_refinement({"event_class": "macro_print"}) == ""
    assert _macro_refinement({}) == ""
    assert _macro_refinement({"macro_tier": "tier2", "macro_economy": "us"}) == "minor"
    assert _macro_refinement({"macro_tier": "tier1", "macro_economy": "us"}) == ""
    assert _macro_refinement({"macro_tier": "tier1", "macro_economy": "foreign"}) == "minor"


def test_the_shipped_config_carries_the_refined_row():
    """The code is inert without it — a fix in code with no config row is dark."""
    import yaml

    cfg = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / "config" / "marketing.yml")
        .read_text(encoding="utf-8"))
    classes = cfg["wire_routing"]["classes"]
    assert classes["macro_print"] == "flagship"
    assert classes["macro_print.minor"] == "mastermind_news"
