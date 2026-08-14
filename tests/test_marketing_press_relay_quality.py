"""W2E — a markets wire does not relay somebody else's copy verbatim.

THE DEFECT, operator-surfaced live on the flagship X account 2026-08-11. Outbox
item ob-2026-08-11-436c0a10aa, kind=breaking, lane=press, created 09:38:27Z,
published 14:39:02Z — the relaunch's first live batch:

    How To Trade SPY, QQQ, AAPL, MSFT, NVDA, GOOGL, META, And TSLA Using
    Technical Analysis

A content-farm SEO listicle, posted word for word. It was not an accident of one
item: 8 of that day's 40 press items shipped in raw register, and the path was
designed in. When the press summarizer produced nothing, `_deterministic_summary`
fell back to ``{headline} -- {source_name}`` and the lane SHIPPED it. A
``::warning title=press-summary-fallback`` had annotated every one of them since
2026-08-04 — loud, correct, and completely ineffective, because a warning that
annotates a post is a receipt, not a gate.

THE POLICY (Voice doctrine v5, docs/marketing_voice_doctrine_v5.md): "no post"
beats "bot post". Three layers, each pinned below against the eight headlines
exactly as they appear in the outbox:

  1. ADMISSION — named non-news families never enter at all
     (relay_hygiene.headline_is_non_news, reached through garbage_gate's
     relay_stub screen): the how-to listicle, the prediction-market clickbait,
     the transcript pointer, and war copy with no market in it.
  2. COMPOSE-OR-DROP — an item whose only available body IS its headline is
     composed by the deterministic macro-print composer, or relayed verbatim
     only where the source's own sentence stands without us, or DROPPED and
     counted. Nothing else ships.
  3. THE SEND-TIME ?-BAN — `copywriter.voice_v5_violations` now bans the
     interrogative for the wire kinds too, which is the queue-vintage half the
     admission screen can never reach.

THE FIXTURES BELOW ARE THE LIVE OUTBOX TEXT, verbatim. Where a test needs a
packet shape (no usable body_snippet), that is also the live shape — an RSS
title with nothing under it is exactly what produced the eight.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine.marketing import copywriter as cw  # noqa: E402
from engine.marketing import garbage_gate as gg  # noqa: E402
from engine.marketing import relay_hygiene as rh  # noqa: E402
from engine.marketing.press_lane import (  # noqa: E402
    _may_relay_verbatim,
    _norm_for_relay_identity,
    compose_macro_print,
    run_press_tick,
)

NOW = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)

# ── The eight, verbatim from outbox items.jsonl on 2026-08-11 ────────────────
F1_UNEMPLOYMENT = "USA Unemployment Rate For July 4.1% Vs 4.2% Est."
F2_PAYROLLS = "Nonfarm Payrolls For July -23K Vs 85K Est.; 20K Prior"
F3_PRIVATE = "Private Nonfarm Payrolls For July 30K Vs 78K Est.; 30K Prior"
F4_LISTICLE = ("How To Trade SPY, QQQ, AAPL, MSFT, NVDA, GOOGL, META, And TSLA "
               "Using Technical Analysis")
F5_PREDICTION = ("US Economy Loses 23,000 Jobs, Gold Jumps 3%: What Do Prediction "
                 "Markets Say About Rate Hikes?")
F6_BARKIN = ("Fed's Barkin Says Fed Will Get Inflation To 2%; Agrees With Warsh "
             "That Inflation Must Be R…")
F7_WENDYS = "Wendy's Q2 Beat Comes with Dividend Cut, Withdrawn Outlook as Sales Slump"
F8_ZELENSKY = ("Zelensky Claims North Korea Sending Up To 50K Troops To Russia, "
               "Presses Seoul To Send Missiles")

#: The same register, one layer further down the timeline — the fallback's
#: " -- {source}" suffix shape, also flagged by the operator the same day.
INVITATION_HOMES = ("Invitation Homes CEO says ban on institutional homebuying "
                    "will bring down prices, but not immediately")

# ── The register that is CORRECT, and must keep flowing ──────────────────────
# Composed relays from the same day's other 32 items. These are the regression
# anchors: a screen that kills the eight and also kills these has not fixed the
# lane, it has closed it.
ANCHOR_HOME_SALES = "US July existing home sales 4.06m vs 4.05m expected"
ANCHOR_HORMUZ = ("Missile strike near the Strait of Hormuz unravels the relief "
                 "trade, Brent +4%")
ANCHOR_JBL = "$JBL is one of the biggest moves on the tape today, up 9.4%"


def _item(headline: str, *, iid: str = "w2e-1", body: str = "",
          source: str = "benzinga", source_name: str = "Benzinga",
          tier: str = "wire", corr: str = "wire", **extra) -> dict:
    row = {
        "id": iid, "source": source, "source_name": source_name,
        "source_tier": tier, "url": f"https://example.test/{iid}",
        "published_at": "2026-08-11T09:38:00Z",
        "headline": headline, "body_snippet": body,
        "corroboration_class": corr,
    }
    row.update(extra)
    return row


def _admission_reason(headline: str) -> str:
    """The drop reason the ingest screen gives this headline, or "" if admitted.

    Goes through `garbage_gate.check` rather than calling the hygiene rule
    directly: what matters is that the P0 screen the lane ACTUALLY runs refuses
    the item, not that a predicate somewhere would have said no.
    """
    drop = gg.check(_item(headline), cfg={}, satire_blocklist=set())
    return "" if drop is None else f"{drop['reason']}:{drop.get('detail', '')}"


def _tick(items: list[dict], **cfg_over) -> dict:
    """One real press tick, dry run, floors lowered.

    The salience floor and the value gate are RELEVANCE policy; this file is
    about register, and a fixture that never reaches composition would pin
    nothing. Everything the tests assert on runs at full strength.
    """
    press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
    press_cfg.setdefault("wire", {})["flagship_salience_floor"] = 0.0
    press_cfg["wire"]["flagship_top_k_per_day"] = 50
    press_cfg["wire"]["rail_salience_floor"] = 0.0
    press_cfg["wire"].update(cfg_over)
    marketing_cfg.setdefault("value_gate", {})["enforce"] = False
    # Isolate from the committed outbox. story_lock.check reads
    # outbox.read_items_all(root); these fixtures ARE the 2026-08-11 live
    # headlines, and NOW is that day's 14:00Z, so a root=REPO tick collides
    # with the flagship items already on disk (story_locked) instead of
    # exercising compose-or-drop. Sibling press tests use tmp_path for the
    # same reason.
    with tempfile.TemporaryDirectory() as tmp:
        return run_press_tick(items, root=tmp, now=NOW, cfg=marketing_cfg,
                              press_cfg=press_cfg, state={}, seen_ids=set(),
                              dry_run=True)


# ═════════════════════════════════════════════════════════════════════════════
# 1. ADMISSION — the named non-news families
# ═════════════════════════════════════════════════════════════════════════════

class TestAdmissionFamilies:
    @pytest.mark.parametrize("headline,family", [
        (F4_LISTICLE, "howto_listicle"),
        ("How To Play The Fed Meeting In 5 Trades", "howto_listicle"),
        ("Top 10 Stocks To Watch In August", "howto_listicle"),
        ("5 Things You Need To Know Before The Bell", "howto_listicle"),
        (F5_PREDICTION, "meta_clickbait"),
        ("What To Expect From The CPI Print", "meta_clickbait"),
        ("Is The Bond Selloff Over?", "meta_clickbait"),
        ("Earnings call transcript: Wendy's Q2 2026", "transcript_furniture"),
        ("Full transcript of the Powell press conference", "transcript_furniture"),
        (F8_ZELENSKY, "unanchored_geopolitics"),
        ("Russia launches missile barrage on Kyiv overnight", "unanchored_geopolitics"),
    ])
    def test_the_family_drops_at_admission(self, headline, family):
        reason = _admission_reason(headline)
        assert reason.startswith("relay_stub:"), (
            f"{headline!r} was ADMITTED; it must die at the P0 screen")
        assert family in reason, f"{headline!r} -> {reason} (expected {family})"

    @pytest.mark.parametrize("headline", [
        # Market content in raw register. It must NOT be killed here — admission
        # judges the SUBJECT, compose-or-drop judges the writing, and conflating
        # them is how a hygiene rule eats the wire.
        F6_BARKIN,
        F7_WENDYS,
        INVITATION_HOMES,
        F1_UNEMPLOYMENT, F2_PAYROLLS, F3_PRIVATE,
        ANCHOR_HOME_SALES, ANCHOR_HORMUZ, ANCHOR_JBL,
        # Ordinary wire copy that merely resembles a banned family.
        "Top Fed official says the cutting cycle is not over",
        "Trade war rhetoric escalates as tariffs hit $300B of goods",
        "Oil holds gains after Hormuz transit resumes, Brent +1.2%",
    ])
    def test_admissible_content_is_not_killed_at_admission(self, headline):
        assert _admission_reason(headline) == "", headline

    def test_the_geopolitics_pair_is_the_whole_rule(self):
        """War copy WITHOUT a market token dies; the same story WITH one lives.

        This pair is the rule. A blanket geopolitics ban would have taken the
        Hormuz relay — the day's best press item — and a rule that only looked at
        `event_class` would have taken neither, because both score `geopolitical`.
        """
        assert rh.headline_is_non_news(F8_ZELENSKY).startswith("unanchored_geopolitics")
        assert rh.headline_is_non_news(ANCHOR_HORMUZ) == ""
        assert not rh.has_market_token(F8_ZELENSKY)
        assert rh.has_market_token(ANCHOR_HORMUZ)

    def test_a_listicle_carrying_tickers_still_dies(self):
        """THE ORDERING PIN. The furniture branch has a market-FIGURE escape, and
        the listicle that motivated this rule names eight tickers — routed through
        that escape it would have been rescued by the very thing that makes it
        spam."""
        assert rh._MARKET_FIGURE_RE.search("Gold Jumps 3%: What Do Prediction Markets Say?")
        assert rh.headline_is_non_news(F4_LISTICLE).startswith("howto_listicle")
        assert rh.headline_is_non_news(F5_PREDICTION).startswith("meta_clickbait")

    def test_a_more_specific_screen_keeps_its_name(self):
        """The generic interrogative rule runs LAST: a calendar index page is
        furniture, and `furniture:` says more about it than "ends in a '?'"."""
        assert rh.headline_is_furniture(
            "What are the main events for today?").startswith("furniture:")

    def test_a_family_can_be_retired_by_config_without_a_deploy(self):
        assert rh.headline_is_non_news(
            F4_LISTICLE, cfg={"non_news_disable": ["howto_listicle"]}) == ""
        assert rh.headline_is_non_news(F4_LISTICLE) != ""


# ═════════════════════════════════════════════════════════════════════════════
# 2. THE DETERMINISTIC MACRO-PRINT COMPOSER
# ═════════════════════════════════════════════════════════════════════════════

class TestMacroPrintComposer:
    @pytest.mark.parametrize("headline,expected", [
        (F1_UNEMPLOYMENT,
         "July unemployment rate: 4.1% against 4.2% expected."),
        (F2_PAYROLLS,
         "July payrolls: -23k against +85k expected. Prior month: +20k."),
        (F3_PRIVATE,
         "July private payrolls: +30k against +78k expected. Prior month: +30k."),
        ("US CPI For June 3.1% Vs 3.0% Est.; 2.9% Prior",
         "June CPI: 3.1% against 3.0% expected. Prior month: 2.9%."),
        ("Retail Sales For Q2 1.2% Vs 0.8% Est.",
         "Q2 retail sales: 1.2% against 0.8% expected."),
    ])
    def test_the_vendor_shape_renders_in_house_register(self, headline, expected):
        assert compose_macro_print(headline) == expected

    def test_a_count_is_signed_and_a_level_is_not(self):
        """NOT COSMETIC. A payroll print is a CHANGE, so "+85k" is the honest
        rendering and a bare "85k" hides half the fact. An unemployment rate is a
        LEVEL, and writing "+4.1%" would assert a move the print does not make."""
        assert "+85k" in compose_macro_print(F2_PAYROLLS)
        assert "-23k" in compose_macro_print(F2_PAYROLLS)
        assert "+4.1%" not in compose_macro_print(F1_UNEMPLOYMENT)
        assert "4.1%" in compose_macro_print(F1_UNEMPLOYMENT)

    def test_the_house_register_carries_none_of_the_vendor_grammar(self):
        for headline in (F1_UNEMPLOYMENT, F2_PAYROLLS, F3_PRIVATE):
            out = compose_macro_print(headline)
            assert "Vs" not in out and " Est." not in out, out
            assert "Prior " not in out.split("Prior month:")[0], out
            assert "K " not in out and not out.endswith("K"), out
            # Subject first: the period and the series open the sentence.
            assert out.split(":")[0].split()[0] in ("July", "June", "Q2"), out

    def test_the_two_payroll_series_never_collapse_into_each_other(self):
        """The alias table shortens "nonfarm payrolls" to "payrolls", and that is
        the one edit in the composer that could MISSTATE rather than mis-style.
        The private series is listed separately precisely so it cannot inherit
        the headline series' name."""
        assert compose_macro_print(F2_PAYROLLS).startswith("July payrolls:")
        assert compose_macro_print(F3_PRIVATE).startswith("July private payrolls:")

    @pytest.mark.parametrize("headline", [
        F4_LISTICLE, F5_PREDICTION, F6_BARKIN, F7_WENDYS, F8_ZELENSKY,
        INVITATION_HOMES,
        "Nonfarm Payrolls For Release Soon Vs Est.",   # no figures
        "Payrolls For July TBD Vs 85K Est.",           # unparseable value
        "Payrolls July -23K Vs 85K Est.",              # no "For <period>"
        "", "   ",
    ])
    def test_an_unrecognised_shape_returns_nothing(self, headline):
        """STRICT ON PURPOSE. This composer is the ONE exception to
        compose-or-drop, so a shape it does not fully recognise must produce
        NOTHING and drop, never a half-rendering."""
        assert compose_macro_print(headline) == ""


# ═════════════════════════════════════════════════════════════════════════════
# 3. COMPOSE-OR-DROP, end to end through the real tick
# ═════════════════════════════════════════════════════════════════════════════

class TestComposeOrDrop:
    @pytest.mark.parametrize("headline", [F1_UNEMPLOYMENT, F2_PAYROLLS, F3_PRIVATE])
    def test_a_macro_print_ships_composed_not_verbatim(self, headline):
        res = _tick([_item(headline, iid=f"macro-{abs(hash(headline)) % 999}")])
        assert res["emitted"], f"the macro print must still ship: {res['skipped']}"
        emit = res["emitted"][0]
        assert emit["source"]["summary_mode"] == "house_macro_print"
        assert "against" in emit["body"] and "expected" in emit["body"]
        assert " Vs " not in emit["body"] and " Est." not in emit["body"]

    @pytest.mark.parametrize("headline,iid,src", [
        (F6_BARKIN, "barkin", ("benzinga", "Benzinga")),
        (F7_WENDYS, "wendys", ("benzinga", "Benzinga")),
        # CNBC is MARQUEE, so this one is creditable and the corroboration gate
        # lets it through to a post — which is exactly why it reached the
        # timeline as "... but not immediately -- CNBC". A creditable source is
        # not a licence to relay its copy.
        (INVITATION_HOMES, "invitation", ("cnbc_top", "CNBC")),
    ])
    def test_admissible_content_drops_when_nothing_composed_it(self, headline, iid, src):
        """Fixtures 6 and 7 are market content the admission screen correctly
        admits. With no summarizer output and no parseable print, there is
        nothing house-written to post, so they drop rather than relay."""
        res = _tick([_item(headline, iid=iid, source=src[0], source_name=src[1])])
        assert res["emitted"] == [], f"{iid} shipped in raw register"
        reasons = {row["reason"] for row in res["skipped"]}
        assert "relay_uncomposed" in reasons, res["skipped"]

    @pytest.mark.parametrize("headline,iid", [
        (F6_BARKIN, "barkin-llm"),
        (F7_WENDYS, "wendys-llm"),
    ])
    def test_the_same_item_ships_once_the_summarizer_composes_it(self, headline, iid):
        """The other half of "compose-OR-drop": the drop is about the WRITING,
        not about the story. Composed, these are exactly the items the lane
        exists to publish."""
        composed = ("Restriction is still building into the front end, and "
                    "nothing in the remarks moved the target away from where it "
                    "already sat.")
        res = _tick_with_llm([_item(headline, iid=iid)], composed)
        assert res["emitted"], f"{iid} must ship once composed: {res['skipped']}"
        assert "Restriction is still building" in res["emitted"][0]["body"]

    def test_a_dropped_relay_says_so_at_line_start(self, capsys):
        """HOUSE LAW: `::warning` must START the line and be flushed. Routed
        through this module's logger the format prefixes it and GitHub silently
        drops the annotation — which is how the 2026-08-04 fallback warning could
        have gone dark without anyone noticing."""
        _tick([_item(F7_WENDYS, iid="wendys-warn")])
        lines = capsys.readouterr().out.splitlines()
        hits = [ln for ln in lines if "press-relay-dropped" in ln]
        assert hits, "the drop must annotate"
        for line in hits:
            assert line.startswith("::warning title=press-relay-dropped::"), line
        assert any(F7_WENDYS[:40] in ln for ln in hits), "name the headline"

    def test_an_attributed_primary_source_quote_still_relays(self):
        """THE EXEMPTION, AND WHY IT IS NOT A LOOPHOLE. `direct-quote` is set by
        exactly two providers (the Truth Social mirrors): the source IS the
        speaker, so the headline is not a publisher's line ABOUT an event, it is
        the event. None of the eight was one — every one was a third-party
        publisher's headline wearing our account's name."""
        quote = "We are placing a 50% tariff on all steel imports effective immediately."
        res = _tick([_item(quote, iid="ts-1", source="trumpstruth",
                           source_name="Truth Social (via trumpstruth.org)",
                           tier="mirror", corr="direct-quote",
                           truth_status_id="ts-1", author="Donald J. Trump")])
        assert res["emitted"], f"a direct quote must still relay: {res['skipped']}"

    def test_a_checkable_squawk_still_relays(self):
        """The 2026-08-04 operator citation law, unretired. "A gold price and a
        direction are checkable off the tape without trusting the relay" — that
        item ships bare, and a blanket "never relay a headline" rule would have
        silently reversed a standing ruling."""
        squawk = ("GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP "
                  "SAID FRESH IRAN TALKS WOULD BEGIN LATER MONDAY")
        ok, why = _may_relay_verbatim(
            {"corroboration_class": "hearsay", "event_class": "none",
             "source_tier": "x_relay", "headline": squawk}, squawk, "")
        assert ok, why

    def test_a_truncated_headline_earns_nothing(self):
        """Fixture 6 ends "Inflation Must Be R…". A cut-off sentence is not a
        sentence in any register, whichever door it came through."""
        ok, why = _may_relay_verbatim(
            {"corroboration_class": "direct-quote", "event_class": "macro_print",
             "source_tier": "official", "headline": F6_BARKIN}, F6_BARKIN, "on the wires")
        assert not ok
        assert "cut off" in why

    def test_a_publisher_editorial_line_earns_nothing(self):
        """Fixture 7's only digit is a quarter label. `self_evident` alone reads
        "Sales Slump" as a market move and says yes — requiring the READING is
        what separates a squawk from copy written to be clicked."""
        from engine.marketing.source_authority import self_evident
        scored = {"corroboration_class": "wire", "event_class": "company_news",
                  "source_tier": "wire", "headline": F7_WENDYS}
        assert self_evident(scored)[0], "pinning WHY the second gate is needed"
        ok, why = _may_relay_verbatim(scored, F7_WENDYS, "")
        assert not ok
        assert "no reading" in why


# ═════════════════════════════════════════════════════════════════════════════
# 4. THE INVARIANT — nothing ships that is just the provider's sentence
# ═════════════════════════════════════════════════════════════════════════════

class TestNothingShipsTheProviderHeadline:
    @pytest.mark.parametrize("headline,iid", [
        (F6_BARKIN, "inv-barkin"),
        (F7_WENDYS, "inv-wendys"),
        (INVITATION_HOMES, "inv-homes"),
        (F4_LISTICLE, "inv-listicle"),
        (F5_PREDICTION, "inv-prediction"),
        (F8_ZELENSKY, "inv-zelensky"),
    ])
    def test_no_emitted_post_is_the_provider_headline(self, headline, iid):
        """THE ACCEPTANCE INVARIANT, checked on the text that actually posts.

        Scoped to copy that did not EARN a verbatim relay — an attributed
        primary-source quote and a checkable squawk are ratified shapes and are
        pinned above. Everything else: if the post is the provider's sentence,
        it did not post.
        """
        res = _tick([_item(headline, iid=iid)])
        provider = _norm_for_relay_identity(headline)
        for emit in res["emitted"]:
            assert _norm_for_relay_identity(emit["body"]) != provider, emit["body"]
            assert _norm_for_relay_identity(emit.get("text", "")) != provider

    def test_the_backstop_catches_the_short_form_with_no_credit(self):
        """THE SECOND ROUTE BACK TO THE HEADLINE, and the one compose-or-drop
        cannot see: the D2 restatement gate degrades a self-restating post to the
        SHORT FORM (headline + credit clause), and an `unnamed` citation tier
        leaves that clause EMPTY. The post is then the provider's sentence even
        though the body it was built from was something else."""
        res = _tick([_item(INVITATION_HOMES, iid="short-form",
                           source="cnbc_top", source_name="CNBC")])
        assert res["emitted"] == []
        reasons = {row["reason"] for row in res["skipped"]}
        assert reasons & {"relay_uncomposed", "relay_restates_headline"}, res["skipped"]


# ═════════════════════════════════════════════════════════════════════════════
# 5. LOSS ACCOUNTING — no silent losses
# ═════════════════════════════════════════════════════════════════════════════

class TestLossAccounting:
    def test_every_drop_lands_in_the_lanes_counters(self):
        """A lane that silently eats stories is the same class of defect as one
        that sprays them. Each drop carries its id, its account, its salience and
        the reason it was refused, so the console can answer "where did the wire
        go" from the tick's own return value."""
        items = [_item(F6_BARKIN, iid="acc-1"),
                 _item(F7_WENDYS, iid="acc-2"),
                 _item(INVITATION_HOMES, iid="acc-3",
                       source="cnbc_top", source_name="CNBC")]
        res = _tick(items)
        rows = [r for r in res["skipped"] if r["reason"] == "relay_uncomposed"]
        assert len(rows) == 3, res["skipped"]
        for row in rows:
            assert row["id"] in {"acc-1", "acc-2", "acc-3"}
            assert row["account"], row
            assert row["headline"], row
            assert row["detail"], "the row must name WHY it could not relay"
            assert row["summary_mode"], row

    def test_the_admission_drops_land_in_blocked(self):
        res = _tick([_item(F4_LISTICLE, iid="blk-1"),
                     _item(F5_PREDICTION, iid="blk-2"),
                     _item(F8_ZELENSKY, iid="blk-3")])
        assert res["emitted"] == []
        blocked = {row["id"]: row["reason"] for row in res["blocked"]}
        assert blocked == {"blk-1": "relay_stub", "blk-2": "relay_stub",
                           "blk-3": "relay_stub"}, res["blocked"]

    def test_the_census_counts_the_drops_and_says_so(self, capsys):
        _tick([_item(F7_WENDYS, iid="cen-1"), _item(F6_BARKIN, iid="cen-2")])
        census = [ln for ln in capsys.readouterr().out.splitlines()
                  if "press-summarizer-census" in ln]
        assert census, "the per-tick census must print"
        assert census[0].startswith("::warning title=press-summarizer-census::")
        assert "dropped_uncomposed=2" in census[0], census[0]


# ═════════════════════════════════════════════════════════════════════════════
# 6. THE COMPOSED REGISTER STILL FLOWS
# ═════════════════════════════════════════════════════════════════════════════

def _tick_with_llm(items: list[dict], text: str) -> dict:
    press_cfg = yaml.safe_load((ROOT / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text())
    press_cfg.setdefault("wire", {})["flagship_salience_floor"] = 0.0
    press_cfg["wire"]["flagship_top_k_per_day"] = 50
    press_cfg["wire"]["rail_salience_floor"] = 0.0
    marketing_cfg.setdefault("value_gate", {})["enforce"] = False
    with tempfile.TemporaryDirectory() as tmp:
        return run_press_tick(items, root=tmp, now=NOW, cfg=marketing_cfg,
                              press_cfg=press_cfg, state={}, seen_ids=set(),
                              dry_run=True, llm_override=lambda item, cfg: text)


class TestComposedAnchorsStillFlow:
    """THE OTHER HALF OF THE ACCEPTANCE. A screen that kills the eight and also
    kills the day's other thirty-two has not fixed the lane, it has closed it.
    These are the composed relays from the same batch, driven end to end through
    the same code path the eight took."""

    @pytest.mark.parametrize("headline,body,composed,iid,pair", [
        (ANCHOR_HOME_SALES,
         "Existing home sales printed 4.06m against a 4.05m consensus. "
         "Inventory sat at 4.2 months and the median price held its level.",
         "Heads up: there is some steady growth here. Inventory sat at 4.2 "
         "months and the median price held its level.", "anch-1", False),
        (ANCHOR_HORMUZ,
         "A missile strike near the Strait of Hormuz sent Brent up 4%. "
         "Insurers repriced war-risk cover on the route and tanker day rates "
         "jumped 18% inside a session.",
         "Crossing now. Insurers repriced war-risk cover on the route and "
         "tanker day rates jumped 18% inside a session.", "anch-2", True),
        (ANCHOR_JBL,
         "$JBL rose 9.4% on the session. Volume ran 4.1 times its twenty-day "
         "average and the guide raise landed before the open.",
         "Volume ran 4.1 times its twenty-day average behind the move, and the "
         "guide raise landed before the open rather than after it.",
         "anch-3", False),
    ])
    def test_the_composed_anchor_ships(self, headline, body, composed, iid, pair):
        # `pair` = a SECOND INDEPENDENT SOURCE, and only the geopolitical anchor
        # needs it. The corroboration law (untouched by this wave) sends a
        # single-source geopolitical claim to the next-morning digest whatever
        # its register, so a one-source Hormuz fixture would go quiet for a
        # reason that has nothing to do with the screens under test.
        items = [_item(headline, iid=iid, body=body,
                       source="cnbc_top", source_name="CNBC")]
        if pair:
            items = [_item(headline, iid=iid, body=body, source="x_zerohedge",
                           source_name="@zerohedge", tier="x_relay",
                           corr="hearsay", x_handle="zerohedge"),
                     _item(headline, iid=f"{iid}-b", body=body,
                           source="x_FirstSquawk", source_name="@FirstSquawk",
                           tier="x_relay", corr="hearsay",
                           x_handle="FirstSquawk")]
        res = _tick_with_llm(items, composed)
        assert res["emitted"], f"{iid} must ship: {res['skipped']}"
        emit = res["emitted"][0]
        assert emit["source"]["summary_mode"].startswith("llm")
        assert _norm_for_relay_identity(emit["body"]) != _norm_for_relay_identity(headline)


# ═════════════════════════════════════════════════════════════════════════════
# 7. THE SEND-TIME ?-BAN (the queue-vintage half)
# ═════════════════════════════════════════════════════════════════════════════

class TestInterrogativeBanReachesTheWire:
    @pytest.mark.parametrize("kind", ["breaking", "press", "hot_tape", "wire"])
    def test_a_question_mark_cannot_post_from_any_wire_lane(self, kind):
        """THE GAP FIXTURE 5 WALKED THROUGH. The screen RAN on it at send time —
        it quarantined other breaking items the same day — and passed it, because
        the interrogative test sat inside the wire exemption."""
        hits = cw.voice_v5_violations(F5_PREDICTION, {"type": kind})
        assert any("question mark" in row for row in hits), (kind, hits)

    def test_the_ban_also_covers_the_wire_ACCOUNT(self):
        hits = cw.voice_v5_violations(F5_PREDICTION,
                                      {"type": "chart", "account": "mastermind_news"})
        assert any("question mark" in row for row in hits), hits

    def test_composed_relays_with_no_question_mark_are_unaffected(self):
        for text in (compose_macro_print(F2_PAYROLLS),
                     "Crossing now. The Strait of Hormuz relief trade unraveled.",
                     "$JBL is one of the biggest moves on the tape today."):
            assert cw.voice_v5_violations(text, {"type": "breaking"}) == [], text

    def test_the_relayed_pronoun_exemption_survives(self):
        """Only the QUESTION half of the wire exemption was retired. A quote is
        the source speaking, and relaying "I" inside one is still honest."""
        quoted = 'Powell: "I would not call this a soft landing."'
        assert not any("first person" in row for row in
                       cw.voice_v5_violations(quoted, {"type": "breaking"}))
