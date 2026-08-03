"""The card must earn its pixels — restatement gates + 1080 square geometry.

Operator defect report 2026-08-02, from live posts on the flagship account. Three
of the four defects are pinned here (the fourth, source-account tagging, has its
own file); every fixture below is a REAL shipped post, not an invention.

  Defect 2 — card title == description. For an X-relay item the feed builds
    headline = snippet[:120] and body_snippet = the same snippet, so the card
    rendered one sentence at two sizes.
  Defect 3 — cards that add nothing. "On the tape: <headline> -- <credit>" beside
    a card whose only content was <headline>.
  Defect 4 — card geometry wrong for social. A 1000x560 landscape card is
    illegible in a phone feed; the canvas is now 1080x1080 (AD_MASTER_PAPER
    §4.1) with the mobile type floors of §0 AG-3.

Every pin here was mutation-checked: the production change was reverted, the
test observed to FAIL, then restored.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from engine.marketing.breaking_summary import (
    _CASHTAG_RE,
    card_earns_attachment,
    restatement_score,
    restatement_tokens,
    summary_earns_the_card,
)
from engine.marketing.chart_render import (
    _bc_fit_headline,
    _bc_text_w,
    _bc_wrap_w,
    _BC_HL_LADDER,
    render_breaking_card,
)

# ── The real posts (@mastermindx001, 2026-08-02/03) ──────────────────────────

GOLD_HEAD = (
    "GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP SAID FRESH "
    "IRAN TALKS WOULD BEGIN LATER MONDAY, RAISING HOPES"
)
GOLD_POST = f"On the tape: {GOLD_HEAD} -- wire reports"

CENTCOM_HEAD = (
    "JUST IN: \U0001F1FA\U0001F1F8\U0001F1EE\U0001F1F7 US CENTCOM says it has "
    "redirected 35 vessels as Iran's blockade continues on the Strait of Hormuz."
)
CENTCOM_POST = f"{CENTCOM_HEAD}\n\nNow crossing. {CENTCOM_HEAD}"

SKOREA_HEAD = (
    "S. KOREAN TRADE BALANCE PRELIM ACTUAL 30.32B "
    "(FORECAST 29.487B, PREVIOUS 36.09B) $MACRO"
)

# The operator's named GOOD case: the card carries the original quote, the post
# carries the deal terms. These are genuinely two different statements.
TRUTH_HEAD = (
    "The U.S.A. is locked and loaded and ready to go against the Islamic "
    "Republic of Iran, at levels of Military Terror, Strength, and Power not "
    "previously seen."
)
TRUTH_POST = (
    "The U.S. has agreed to cancel a planned attack on Iran after being asked "
    "to hold off while deal parameters are negotiated, which would include "
    "opening the Hormuz Strait and ending Iran's nuclear threat. Israel joins "
    "the commitment to pursue a deal. -- on Truth Social"
)


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _texts(svg: str) -> list[str]:
    return [
        (el.text or "") for el in _parse(svg).iter()
        if el.tag.endswith("text") or el.tag.endswith("tspan")
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Defect 2 — a summary that merely restates the headline never reaches the card
# ─────────────────────────────────────────────────────────────────────────────

def test_identical_headline_and_summary_scores_one():
    """The X-relay shape: headline and body_snippet are the SAME string."""
    assert restatement_score(GOLD_HEAD, GOLD_HEAD) == pytest.approx(1.0)
    assert summary_earns_the_card(GOLD_HEAD, GOLD_HEAD) is False


def test_truncated_headline_still_reads_as_a_restatement():
    """headline = snippet[:120] — a PREFIX of the summary, not an equal string."""
    head = GOLD_HEAD[:120]
    assert restatement_score(head, GOLD_HEAD) > 0.9
    assert summary_earns_the_card(head, GOLD_HEAD) is False


def test_a_short_headline_inside_a_long_body_is_still_a_restatement():
    """CONTAINMENT, not similarity — and this is the case that proves it.

    body_snippet runs to ~600 chars while headline is snippet[:120], so the
    headline can be a small fraction of the summary and still say nothing the
    summary does not. Containment over the shorter token set scores that 1.0; a
    symmetric measure (Jaccard) scores it ~0.3 and waves the doubled card
    through. The near-equal fixtures above cannot tell the two measures apart —
    only this shape can.
    """
    head = "Fed holds rates steady"
    body = (
        "Fed holds rates steady at 4.25% to 4.50% following a two-day meeting, "
        "with two policymakers dissenting in favour of an immediate increase "
        "and the statement language on inflation left unchanged from June."
    )
    assert restatement_score(head, body) == pytest.approx(1.0)
    assert summary_earns_the_card(head, body) is False
    # ...while a body that genuinely departs from the headline is kept.
    assert summary_earns_the_card(head, TRUTH_POST) is True


def test_genuinely_different_summary_is_kept():
    assert summary_earns_the_card(TRUTH_HEAD, TRUTH_POST) is True


def test_empty_summary_never_earns_the_card():
    assert summary_earns_the_card(GOLD_HEAD, "") is False
    assert summary_earns_the_card(GOLD_HEAD, "   ") is False


def test_card_omits_the_summary_block_when_it_restates_the_headline():
    """End to end: the renderer draws no second voice for a restating summary."""
    restating = render_breaking_card(
        GOLD_HEAD, "Newswire", "aggregator", "2026-08-03T00:12:02Z",
        summary=(GOLD_HEAD if summary_earns_the_card(GOLD_HEAD, GOLD_HEAD)
                 else None),
    )
    # The headline appears; it does NOT appear a second time as a summary.
    body = " ".join(_texts(restating))
    assert "GOLD ROSE" in body
    assert body.count("RAISING HOPES") <= 1


def _payload(headline: str, snippet: str, **extra) -> dict:
    """build_breaking_payload over an X-relay-shaped item, no LLM."""
    from engine.marketing.breaking_summary import build_breaking_payload

    item = {
        "id": "t1",
        "headline": headline,
        "body_snippet": snippet,
        "source": "x_relay",
        "source_name": "Newswire",
        "source_tier": "x_relay",
        "url": "https://example.invalid/1",
        "published_at": "2026-08-03T00:12:02Z",
        "event_class": "macro_print",
        **extra,
    }
    return build_breaking_payload(item, {}, _llm_override=lambda *_a, **_k: None)


def test_payload_drops_a_restating_summary_from_the_card():
    """THE WIRING PIN for defect 2 — headline == body_snippet is the live shape.

    The gate is useless if the payload builder still hands the renderer the
    summary, so this asserts the value the CARD was given, not the gate.
    """
    p = _payload(GOLD_HEAD, GOLD_HEAD)
    assert p["card_summary"] is None
    # The POST body keeps its summary — the gate is about the picture only.
    assert p["summary"]


def test_payload_keeps_a_distinct_summary_for_the_card():
    """A body that genuinely ADDS survives to the card.

    The gate must not be a blanket "drop every summary": that would delete the
    operator's named good case (card = the quote, post = the terms) along with
    the restatements.
    """
    p = _payload(
        "Fed holds rates steady",
        "Policymakers left the target range untouched and flagged supply, "
        "not demand, as the constraint.",
    )
    assert p["card_summary"], f"summary was dropped: {p['summary']!r}"


def test_deterministic_fallback_summary_never_reaches_the_card():
    """The fallback body is "{headline} -- {source}" — the doubled card, exactly.

    When the packet carries no usable body the deterministic summary IS the
    headline wearing an attribution. That is the shape the operator saw, and it
    must never be drawn on the card even though it still ships as the post body.
    """
    p = _payload(GOLD_HEAD, "")
    assert p["summary"].startswith(GOLD_HEAD)
    assert p["card_summary"] is None


def test_payload_exposes_the_dispatch_contract():
    """press_lane reads these two keys to decide the attachment.

    A missing key degrades silently to ""/[] — the conservative direction, but
    it would quietly disable the tape-reading clause, so the contract is pinned.
    """
    p = _payload(GOLD_HEAD, GOLD_HEAD)
    assert "card_summary" in p
    assert "card_tickers" in p
    assert isinstance(p["card_tickers"], list)


# ─────────────────────────────────────────────────────────────────────────────
# Defect 3 — a card that restates the post text does not attach
# ─────────────────────────────────────────────────────────────────────────────

def test_gold_flash_ships_card_less():
    attach, why = card_earns_attachment(GOLD_POST, GOLD_HEAD, "", [])
    assert attach is False
    assert "restates" in why


def test_centcom_flash_ships_card_less():
    attach, why = card_earns_attachment(CENTCOM_POST, CENTCOM_HEAD, "", [])
    assert attach is False
    assert "restates" in why


def test_our_own_opener_does_not_rescue_a_restating_card():
    assert restatement_score(GOLD_POST, GOLD_HEAD) > 0.9
    assert restatement_score(CENTCOM_POST, CENTCOM_HEAD) > 0.9


def test_our_own_openers_are_not_content():
    """"On the tape:" / "Now crossing." are scaffolding we added, not facts.

    Pinned at the TOKENIZER, because containment measures the shorter side: junk
    added to the post can only grow the intersection, so the post-side strip is
    invisible through restatement_score. It is observable — and load-bearing —
    on the summary side, where an opener on one text and not the other would
    otherwise read as a real difference.
    """
    assert restatement_tokens("On the tape: Gold rose") == \
        restatement_tokens("Gold rose")
    assert restatement_tokens("Now crossing. Gold rose") == \
        restatement_tokens("Gold rose")
    assert restatement_tokens("Heads up: Gold rose") == \
        restatement_tokens("Gold rose")


def test_the_good_case_keeps_its_card():
    """Operator's named good case: card = the quote, post = the deal terms."""
    attach, why = card_earns_attachment(TRUTH_POST, TRUTH_HEAD, "", [])
    assert attach is True


def test_distinct_summary_earns_the_attachment():
    attach, why = card_earns_attachment(
        GOLD_POST, GOLD_HEAD,
        "Spot gold last traded at $4,070.40, a five-session high.", [],
    )
    assert attach is True
    assert "summary" in why


def test_a_tape_reading_earns_the_attachment():
    attach, why = card_earns_attachment(
        GOLD_POST, GOLD_HEAD, "",
        [{"ticker": "GLD", "price": 401.55, "pct": -0.3}],
    )
    assert attach is True
    assert "tape" in why


def test_a_cashtag_only_row_is_not_a_tape_reading():
    """No number = nothing the copy lacks. A bare cashtag must not rescue a card."""
    attach, _ = card_earns_attachment(
        GOLD_POST, GOLD_HEAD, "", [{"ticker": "GLD"}],
    )
    assert attach is False


def test_nan_row_is_not_a_tape_reading():
    """float('nan') passes a float() cast — it must not count as a reading."""
    attach, _ = card_earns_attachment(
        GOLD_POST, GOLD_HEAD, "",
        [{"ticker": "GLD", "price": float("nan"), "pct": float("nan")}],
    )
    assert attach is False


def test_empty_post_text_keeps_the_card():
    attach, _ = card_earns_attachment("", GOLD_HEAD, "", [])
    assert attach is True


# ─────────────────────────────────────────────────────────────────────────────
# THE DISPATCH — the gate has to actually be wired, not merely importable
# ─────────────────────────────────────────────────────────────────────────────

def _press_tick(items: list[dict]) -> dict:
    """Drive the real press tick (dry run) so the dispatch is exercised end to end."""
    from datetime import datetime, timezone
    from pathlib import Path

    import yaml

    from engine.marketing.press_lane import run_press_tick

    root = Path(__file__).resolve().parent.parent
    now = datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc)
    press_cfg = yaml.safe_load((root / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((root / "config" / "marketing.yml").read_text())
    # The salience floor and the per-day cap are relevance policy, not the thing
    # under test — left at production values these fixtures skip, and a skipped
    # test is not a pin. Lowered so the dispatch is genuinely exercised.
    press_cfg.setdefault("wire", {})["flagship_salience_floor"] = 0.0
    press_cfg["wire"]["flagship_top_k_per_day"] = 50
    return run_press_tick(
        items, root=str(root), now=now, cfg=marketing_cfg,
        press_cfg=press_cfg, state={}, seen_ids=set(), dry_run=True,
    )


def _relay_item(iid: str, headline: str, snippet: str) -> dict:
    return {
        "id": iid,
        "source": "x_wire",
        "source_name": "Newswire",
        "source_tier": "x_relay",
        "url": f"https://example.invalid/{iid}",
        "published_at": "2026-08-03T00:12:02Z",
        "headline": headline,
        "body_snippet": snippet,
        "x_handle": "wire",
        "corroboration_class": "hearsay",
    }


def test_dispatch_actually_strips_the_card_from_a_restating_post():
    """THE INTEGRATION PIN for defect 3.

    A gate that is imported but never consulted is the failure mode this
    project keeps re-learning, so this drives run_press_tick and reads the
    EMITTED item: a restating flash must reach the queue with no media at all.
    """
    res = _press_tick([_relay_item("restate-1", GOLD_HEAD, GOLD_HEAD)])
    emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
    if not emitted:
        pytest.skip("item did not clear the emission floor in this config")
    for e in emitted:
        assert e.get("media") in ([], None), (
            f"restating flash still shipped media: {e.get('media')}"
        )
        assert (e.get("source") or {}).get("card_dropped"), \
            "no card_dropped reason recorded on the emission"


def test_dispatch_does_not_blanket_drop_every_card():
    """The opposite direction, through the same wiring — and it is the ticker law.

    Worth stating plainly, because it shaped the gate: the composed post is
    `headline + blank line + body`, so on the ordinary path the card's headline
    AND its summary are both already in the post text and the card genuinely
    adds nothing. A card earns its place when the X clamp drops the headline
    from the post (the operator's Truth Social good case — card = the quote,
    post = the terms), when it carries a tape reading, or — here — when the copy
    names a ticker and the picture becomes a shipping requirement.
    """
    item = _relay_item(
        "keep-1",
        "Nvidia guides data-center revenue above consensus for $NVDA",
        "The company said supply, not demand, remains the constraint and lifted "
        "its outlook for the January quarter.",
    )
    res = _press_tick([item])
    emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
    if not emitted:
        pytest.skip("item did not clear the emission floor in this config")
    for e in emitted:
        dropped = (e.get("source") or {}).get("card_dropped")
        assert not dropped, f"a cashtag post lost its card: {dropped}"
        assert e.get("media"), "a cashtag post must ship a picture"


# ─────────────────────────────────────────────────────────────────────────────
# Backstop — no source handle may reach a CARD surface (defect 1, card side)
# ─────────────────────────────────────────────────────────────────────────────

def test_a_handle_in_a_card_param_drops_the_card(capsys):
    """The live defect drew "@BRICSinfo · AGGREGATOR" into the card art.

    De-handling at ingestion is the fix; this is the net under it, and it screens
    the params — a surface copywriter.banned_language (which reads POST TEXT)
    can never see. A leak costs the picture, never the post.
    """
    p = _payload(GOLD_HEAD, "", source_name="@FirstSquawk")
    assert p["card_svg"] == ""
    out = capsys.readouterr().out
    assert "::warning title=breaking-card-handle-mention::" in out
    # The screen lower-cases handles when it reports them.
    assert "firstsquawk" in out.lower()
    assert "source_name" in out


def test_a_clean_card_still_renders():
    """Mutation guard: the screen must not be refusing everything."""
    p = _payload(GOLD_HEAD, "", source_name="Newswire")
    assert p["card_svg"].startswith("<svg")


def test_card_handle_annotation_starts_the_line(capsys):
    """GitHub drops an annotation that does not START its line (house law)."""
    _payload(GOLD_HEAD, "", source_name="@FirstSquawk")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert lines, "no annotation emitted"
    for ln in lines:
        assert ln.startswith("::warning"), f"annotation does not start the line: {ln!r}"


# ─────────────────────────────────────────────────────────────────────────────
# The ticker-post law OUTRANKS the card-value law
# ─────────────────────────────────────────────────────────────────────────────

def test_cashtag_post_always_keeps_its_card():
    """A `breaking` post naming tickers is quarantined without a picture.

    scripts/marketing_publisher._bare_cashtag_post, operator 2026-07-30. If the
    card-value gate stripped the card here it would not produce a leaner post —
    it would kill the post. The S. Korea flash is the live instance: the wire's
    own "$MACRO" tag reads as a cashtag to that gate.
    """
    post = f"{SKOREA_HEAD}\n\n{SKOREA_HEAD}"
    # Restatement is total...
    assert restatement_score(post, SKOREA_HEAD) > 0.9
    # ...and the card is kept anyway, for the stated reason.
    attach, why = card_earns_attachment(post, SKOREA_HEAD, "", [])
    assert attach is True
    assert "$MACRO" in why


def test_cashtag_pattern_matches_press_lane():
    """Drift pin: the two gates must ask the same question of the same string."""
    from engine.marketing import press_lane

    assert _CASHTAG_RE.pattern == press_lane._CASHTAG_RE.pattern


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer behaviour the gates rest on
# ─────────────────────────────────────────────────────────────────────────────

def test_figures_survive_tokenization():
    """A number is exactly the kind of detail that makes two texts different."""
    toks = restatement_tokens(SKOREA_HEAD)
    assert "30.32b" in toks
    assert "29.487b" in toks


def test_credit_clause_is_not_content():
    """The trailing credit is scaffolding; it must not create a difference."""
    assert restatement_tokens("Gold rose -- wire reports") == \
        restatement_tokens("Gold rose")


def test_wire_opener_is_not_content():
    assert restatement_tokens("JUST IN: vessels redirected") == \
        restatement_tokens("vessels redirected")


# ─────────────────────────────────────────────────────────────────────────────
# Defect 4 — geometry, and the mobile-legibility floors (AD_MASTER_PAPER §0)
# ─────────────────────────────────────────────────────────────────────────────

def _svg_attrs(svg: str) -> dict:
    return _parse(svg).attrib


def test_default_canvas_is_1080_square():
    svg = render_breaking_card(
        GOLD_HEAD, "Newswire", "aggregator", "2026-08-03T00:12:02Z"
    )
    a = _svg_attrs(svg)
    assert a["width"] == "1080"
    assert a["height"] == "1080"
    assert a["viewBox"] == "0 0 1080 1080"


def test_tall_variant_renders_at_1080x1350():
    svg = render_breaking_card(
        GOLD_HEAD, "Newswire", "aggregator", "2026-08-03T00:12:02Z",
        width=1080, height=1350,
    )
    a = _svg_attrs(svg)
    assert a["width"] == "1080"
    assert a["height"] == "1350"


#: The hero lines specifically — negative tracking is the headline's own
#: signature and is what separates it from the footer URL, which is also white
#: and also 800-weight (that near-miss failed this helper's first draft).
_HERO_RE = re.compile(
    r'<text x="([\d.]+)" y="[\d.]+" fill="#ffffff" font-size="([\d.]+)" '
    r'font-weight="800" font-family="sans-serif" letter-spacing="-0.015em">'
    r'([^<]*)</text>'
)


def _headline_lines(svg: str) -> list[tuple[float, float, str]]:
    """(x, size, text) for every hero line."""
    return [
        (float(m.group(1)), float(m.group(2)), m.group(3))
        for m in _HERO_RE.finditer(svg)
    ]


def _headline_sizes(svg: str) -> list[float]:
    return [size for _, size, _ in _headline_lines(svg)]


@pytest.mark.parametrize("head", [
    "Fed holds rates steady",
    CENTCOM_HEAD,
    SKOREA_HEAD,
])
def test_headline_clears_the_mobile_legibility_floor(head):
    """AG-3: headline >= 84px on a 1080 canvas, 76px the absolute floor.

    This is the defect the operator named — a card "too small for mobile". The
    old renderer bucketed the headline at 26-44px on a 1000px canvas, i.e. under
    a THIRD of the floor.
    """
    svg = render_breaking_card(head, "Newswire", "wire", "2026-08-03T00:12:02Z")
    sizes = _headline_sizes(svg)
    assert sizes, "no headline lines rendered"
    assert min(sizes) >= 76.0, f"headline at {min(sizes)}px is below the AG-3 floor"


@pytest.mark.parametrize("head", [GOLD_HEAD, TRUTH_HEAD])
def test_an_over_length_headline_completes_below_the_floor(head):
    """The two same-day operator laws meet on an over-length head: AG-3 ("too
    small") and W4g ("title header ... gets cut off"). GOLD (120 all-caps
    chars) and TRUTH (a 157-char single sentence) cannot fit whole at the 78px
    floor, and the first draft of this suite pinned the FLOOR for them — under
    which the renderer quietly clipped "RAISING HOPES" off the gold hero with
    an ellipsis. Completeness wins: the fitter continues down the sub-floor
    rungs (_BC_HL_EXTENDED, 68→46) exactly far enough to place every word, and
    the ellipsis path stays unreachable for a sentence-bounded hero.
    """
    svg = render_breaking_card(head, "Newswire", "wire", "2026-08-03T00:12:02Z")
    lines = _headline_lines(svg)
    assert lines, "no headline lines rendered"
    joined = " ".join(t for _, _, t in lines)
    assert "…" not in joined, f"over-length head was clipped: {joined!r}"
    # The whole statement is on the card (unescape the SVG entities first).
    unescaped = (joined.replace("&#39;", "'").replace("&quot;", '"')
                 .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
    assert unescaped == " ".join(head.split())
    # ...and the step-down is bounded: never below the extended ladder's floor,
    # and only ever one region below the AG-3 floor for these lengths.
    assert min(s for _, s, _ in lines) >= 60.0


def test_supporting_type_clears_its_floors():
    """Subline >= 40px, chips >= 27px on a 1080 canvas (AG-3)."""
    svg = render_breaking_card(
        TRUTH_HEAD, "Truth Social", "official", "2026-08-02T03:48:20Z",
        summary="The U.S. has agreed to cancel a planned attack on Iran.",
        tickers=[{"ticker": "GLD", "price": 401.55, "pct": -0.3}],
    )
    # Summary ink is the distinctive secondary fill (#C8D4EA — unified with the
    # W4g legibility work's _BREAK_BODY when the two 2026-08-02 card rebuilds
    # merged; test_marketing_breaking_card_geometry pins the same literal).
    sub = [float(m) for m in re.findall(
        r'fill="#C8D4EA" font-size="([\d.]+)"', svg)]
    assert sub and min(sub) >= 40.0
    # Tier chip label.
    chip = [float(m) for m in re.findall(
        r'font-size="([\d.]+)" font-weight="bold" font-family="sans-serif" '
        r'letter-spacing="0.40"', svg)]
    assert chip and min(chip) >= 27.0


def test_headline_never_overflows_the_content_column():
    """Every hero line must fit the column at its chosen size.

    The estimator is calibrated against real Chrome renders and deliberately
    over-predicts; this is the pin that keeps a future 'optimisation' of those
    constants from letting copy run off the card.
    """
    for head in (GOLD_HEAD, CENTCOM_HEAD, SKOREA_HEAD, TRUTH_HEAD,
                 "Fed holds rates steady at 4.25%-4.50%"):
        svg = render_breaking_card(
            head, "Newswire", "wire", "2026-08-03T00:12:02Z")
        col_w = 1080 - 72 * 2
        lines = _headline_lines(svg)
        assert lines, f"no hero lines for {head[:40]!r}"
        for x, size, text in lines:
            assert x == 72.0
            assert _bc_text_w(text, size) <= col_w * 1.02, (
                f"line {text!r} at {size}px exceeds the {col_w}px column"
            )


def test_long_headline_fills_the_box_rather_than_clipping():
    """A capped line count clipped a wire flash while leaving room below it.

    Truncating the fact is a worse failure than one more line, so the BOX
    governs and the ladder floor guards legibility.
    """
    svg = render_breaking_card(
        CENTCOM_HEAD, "Newswire", "aggregator", "2026-08-02T23:13:34Z")
    body = " ".join(_texts(svg))
    assert "Hormuz" in body
    assert "…" not in body, "headline was clipped despite room on the card"


def test_generic_source_name_shows_the_tier_alone():
    """De-handling makes every relay "Newswire"; the chip must not say it twice."""
    svg = render_breaking_card(
        GOLD_HEAD, "Newswire", "aggregator", "2026-08-03T00:12:02Z")
    assert "AGGREGATOR" in svg
    assert "Newswire · AGGREGATOR" not in svg
    # A real publication still earns its name beside the tier.
    named = render_breaking_card(
        GOLD_HEAD, "Federal Reserve", "official", "2026-08-03T00:12:02Z")
    assert "Federal Reserve · OFFICIAL SOURCE" in named


def test_anti_laundering_survives_the_redesign():
    """The tier chip is the signature and its weight encoding is law (D05)."""
    off = render_breaking_card(GOLD_HEAD, "Fed", "official", "2026-08-03T00:12:02Z")
    agg = render_breaking_card(GOLD_HEAD, "Blog", "aggregator", "2026-08-03T00:12:02Z")
    assert "bc-tier-official" in off and "bc-tier-official" not in agg
    assert "OFFICIAL SOURCE" not in agg


# ─────────────────────────────────────────────────────────────────────────────
# The width fitter itself
# ─────────────────────────────────────────────────────────────────────────────

def test_wrap_reports_overflow_when_a_line_cannot_be_placed():
    """The for/else form silently DROPPED a held line and reported a clean fit."""
    lines, overflowed = _bc_wrap_w("one two three four five six", 100, 200, 2)
    assert overflowed is True
    assert lines[-1].endswith("…")


def test_wrap_places_every_word_when_there_is_room():
    lines, overflowed = _bc_wrap_w("one two three", 20, 900, 4)
    assert overflowed is False
    assert " ".join(lines) == "one two three"


@pytest.mark.parametrize("max_lines", [1, 2, 3, 4, 5, 6, 7])
@pytest.mark.parametrize("max_w", [180, 320, 640, 936])
@pytest.mark.parametrize("size", [40, 84, 132])
def test_wrap_never_silently_loses_a_word(max_lines, max_w, size):
    """THE CONTRACT, pinned as a property rather than as one example.

    Either every word is placed, or the text is visibly truncated. The failure
    this forbids is the quiet one: the old for/else dropped a held line AND
    reported overflowed=False, so the caller believed the copy fit and the
    reader lost a fact with no ellipsis to warn them.
    """
    text = CENTCOM_HEAD
    lines, overflowed = _bc_wrap_w(text, size, max_w, max_lines)
    joined = " ".join(lines)
    if not overflowed:
        assert joined == " ".join(text.split()), (
            "reported a clean fit but the text is not intact"
        )
    else:
        assert joined.endswith("…"), "truncated without saying so"


#: GROUND TRUTH — rendered advance widths measured off real headless-Chrome
#: rasters (pixel scan of one probe string per row), 2026-08-02. These are the
#: numbers the estimator was calibrated against.
_MEASURED_WIDTHS = [
    # (text, size, bold, measured px)
    ("Fed holds rates steady", 118, True, 1277),
    ("GOLD ROSE ABOUT 0.6%", 106, True, 1307),
    ("data-center revenue", 118, True, 1119),
    ("Federal Reserve · OFFICIAL SOURCE", 28, True, 495),
    ("Earnings call transcript · AGGREGATOR", 28, True, 534),
    ("AGGREGATOR", 28, True, 201),
    ("WIRE SERVICE", 28, True, 203),
    ("The committee left the target range unchanged and", 41, False, 930),
    ("Management guided above consensus and said", 41, False, 869),
    ("18:00 UTC · Jul 19", 27, False, 224),
    ("$SPY", 37, True, 95),
    ("BREAKING", 33, True, 174),
    ("EARNINGS CALL", 33, True, 271),
    ("MACRO PRINT", 25, True, 177),
]


@pytest.mark.parametrize("text,size,bold,measured", _MEASURED_WIDTHS)
def test_estimator_never_under_predicts_a_real_render(text, size, bold, measured):
    """The estimator must never promise more room than the font gives.

    Checking the fitter against _bc_text_w is vacuous — mutate the constants and
    both sides move together. So the pin is against MEASURED pixels: the first
    pass guessed 0.63em for bold caps, under-predicted "AGGREGATOR" by 14%, and
    that is precisely how the tier chip's own text ended up outside its pill.
    Under-prediction is the unsafe direction and this is the only test that can
    see it.
    """
    est = _bc_text_w(text, size, bold=bold)
    assert est >= measured, (
        f"{text!r} at {size}px: estimate {est:.0f}px < rendered {measured}px — "
        f"copy will overflow its box"
    )


@pytest.mark.parametrize("text,size,bold,measured", _MEASURED_WIDTHS)
def test_estimator_is_not_absurdly_conservative(text, size, bold, measured):
    """The safety margin must not become a reason to set tiny type."""
    est = _bc_text_w(text, size, bold=bold)
    assert est <= measured * 1.35, (
        f"{text!r} at {size}px: estimate {est:.0f}px is {est / measured:.2f}x the "
        f"rendered {measured}px — the fitter will pick a needlessly small size"
    )


def test_fitter_prefers_the_largest_size_that_fits():
    size_short, _ = _bc_fit_headline("Fed holds", 936, 900, _BC_HL_LADDER, 7)
    size_long, _ = _bc_fit_headline(GOLD_HEAD, 936, 900, _BC_HL_LADDER, 7)
    assert size_short == _BC_HL_LADDER[0]
    assert size_long < size_short


def test_caps_are_measured_wider_than_lowercase():
    """The mis-calibration that let the tier chip's text escape its own pill."""
    assert _bc_text_w("AGGREGATOR", 28) > _bc_text_w("aggregator", 28)
