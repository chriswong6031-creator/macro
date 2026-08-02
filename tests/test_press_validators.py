"""tests/test_press_validators.py — D14 W1 press validator suite.

The suite exists because an LLM wrote the thing being checked.  Every test here
pins a DEFECT the validator has to catch, not a happy path it happens to allow:
a lifted paragraph, an originated number, a padded piece that clears the
our-value floor on vibes, a fabricated quotation, the machine's own vocabulary.

Every test is offline and writes nothing outside tmp_path (MM_DATA_GUARD law).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.press import validators as V  # noqa: E402
from tests import press_fixtures as F  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# close-paraphrase — the headline requirement
# ─────────────────────────────────────────────────────────────────────────────


def test_lifted_paragraph_fails_close_paraphrase():
    """A paragraph copied out of the source must be caught."""
    row = V.check_close_paraphrase(
        F.draft(F.LIFTED_PARAGRAPH), F.slot(), F.config())
    assert row["ok"] is False, row["detail"]
    assert row["metrics"]["max_block_jaccard"] > row["metrics"]["threshold"]
    assert "research_vault:demo-report" in row["metrics"]["worst_source"]


def test_rewritten_same_facts_passes_close_paraphrase():
    """The same facts, actually rewritten, must sail through."""
    row = V.check_close_paraphrase(
        F.draft(F.REWRITTEN_PARAGRAPH), F.slot(), F.config())
    assert row["ok"] is True, row["detail"]
    assert row["metrics"]["max_block_jaccard"] <= row["metrics"]["threshold"]


def test_close_paraphrase_reports_the_unwindowed_number_too():
    """`doc_jaccard` is the spec's plain document-level figure — reported, not
    gated.  Its presence is what lets an operator see WHY the windowed number is
    the one with teeth."""
    # A REALISTIC piece: one lifted paragraph inside a full-length article.
    d = F.draft(*F.FILLER_PARAGRAPHS, F.LIFTED_PARAGRAPH)
    row = V.check_close_paraphrase(d, F.slot(), F.config())
    m = row["metrics"]
    assert "doc_jaccard" in m
    # The whole point of windowing: the document-level number for the SAME
    # lifted text is below the threshold and would have shipped the piece.
    assert m["doc_jaccard"] < m["threshold"] < m["max_block_jaccard"]
    assert row["ok"] is False


def test_quoted_span_is_excluded_from_paraphrase_shingles():
    """A verbatim quotation is supposed to be verbatim; scoring it as paraphrase
    would punish the honest form.  Quote-lint bounds the loophole separately."""
    short_quote = " ".join(F.LIFTED_PARAGRAPH.split()[:20])
    quoted = f'The desk put it plainly: "{short_quote}."'
    unquoted = f"The desk put it plainly: {short_quote}."
    cfg, slot = F.config(), F.slot()
    assert V.check_close_paraphrase(F.draft(quoted), slot, cfg)["ok"] is True
    assert V.check_close_paraphrase(F.draft(unquoted), slot, cfg)["ok"] is False


def test_close_paraphrase_passes_when_no_source_document_supplied():
    row = V.check_close_paraphrase(
        F.draft("A short original paragraph about nothing in particular."),
        F.slot(raw_documents=[]), F.config())
    assert row["ok"] is True
    assert "no raw source document" in row["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# our-value
# ─────────────────────────────────────────────────────────────────────────────

_OURS = ("Our own market-state composite reads 56 out of 100, which is the "
         "middle of its range and not a level that has historically preceded "
         "much of anything on its own.")
_THEIRS = ("The desk's number is 120 dollars for the December contract, and it "
           "gets there through supply rather than through demand, which is a "
           "different claim than it first appears.")
_PADDING = ("What follows is context for readers who have not been watching "
            "this corner of the market closely over recent sessions.")


def test_our_value_share_is_computed_from_sentence_word_counts():
    d = F.draft(_OURS, _THEIRS, _PADDING, fold=False, byline=False, footer=False)
    row = V.check_our_value(d, F.slot(), F.config())
    m = row["metrics"]

    ours = V.word_count(_OURS)
    total = ours + V.word_count(_THEIRS) + V.word_count(_PADDING)
    assert m["our_words"] == ours
    assert m["total_words"] == total
    assert m["our_value_share"] == pytest.approx(ours / total, abs=1e-4)
    assert m["granularity"] == "sentence"

    tiers = [b["tier"] for b in m["sentences"]]
    assert tiers == ["first_party", "other", "neutral"]


def test_our_value_is_not_moved_by_paragraph_boundaries():
    """THE DEFECT THIS CLOSES: at block granularity, one anchored number carried
    its WHOLE block, so the score measured the author's use of the Enter key.
    The reviewer moved identical prose from 0.0345 to 1.0 by splitting
    paragraphs. Same words, same numbers, different formatting — same score."""
    anchored = "Our composite reads 56 today."
    filler = (" It is the middle of its range. Nobody should read much into a "
              "single session. The useful question is what would change it. "
              "That question has a numeric answer and this sentence is not it.")

    one_block = F.draft(anchored + filler, fold=False, byline=False, footer=False)
    many_blocks = F.draft(anchored, *[s.strip() for s in filler.split(". ") if s.strip()],
                          fold=False, byline=False, footer=False)

    a = V.check_our_value(one_block, F.slot(), F.config())["metrics"]["our_value_share"]
    b = V.check_our_value(many_blocks, F.slot(), F.config())["metrics"]["our_value_share"]
    assert a == pytest.approx(b, abs=0.02), (a, b)
    assert a < 0.4, "one number must not carry four sentences of filler"


def test_a_decimal_receipt_is_not_split_into_two_sentences():
    """"65.7" must stay one number: a sentence splitter that fires on any period
    would cut it in half and the receipt would vanish."""
    assert V.sentences("The scare scores 65.7 today. It was lower.") == [
        "The scare scores 65.7 today.", "It was lower."]


# ── receipts floor ───────────────────────────────────────────────────────────


def test_receipts_floor_rejects_a_piece_carrying_one_lucky_number():
    slot = F.slot(min_anchored_receipts=5)
    row = V.check_receipts(F.draft(_OURS, fold=False), slot, F.config())
    assert row["ok"] is False
    assert row["metrics"]["receipts"] < 5 and row["metrics"]["minimum"] == 5


def test_receipts_floor_counts_distinct_values_not_repetitions():
    """Saying 56 five times is one receipt, not five."""
    slot = F.slot(min_anchored_receipts=2)
    repeated = F.draft("The composite is 56. Still 56. Again 56. Yes, 56.",
                       fold=False)
    assert V.check_receipts(repeated, slot, F.config())["metrics"]["receipts"] == 1
    both = F.draft("The composite is 56 and the scare scores 65.7.", fold=False)
    assert V.check_receipts(both, slot, F.config())["ok"] is True


def test_receipts_floor_comes_from_the_desk():
    cfg = F.config()
    assert cfg["desks"]["brief"]["min_anchored_receipts"] == 5
    assert cfg["desks"]["research_desk"]["min_anchored_receipts"] == 4


def test_our_value_is_always_printed_into_the_report():
    report = V.validate(F.draft(_OURS), F.slot(), F.config(), root=_REPO)
    assert report["our_value_share"] is not None
    assert any(c["name"] == "our_value" for c in report["checks"])


def test_padding_only_piece_cannot_reach_the_our_value_floor():
    """A block with no numbers counts toward the denominator only — otherwise
    filler prose would carry a piece over the floor."""
    row = V.check_our_value(
        F.draft(_PADDING, _PADDING, _PADDING, fold=False, byline=False, footer=False),
        F.slot(), F.config())
    assert row["metrics"]["our_value_share"] == 0.0
    assert row["ok"] is False


def test_third_party_only_sentence_does_not_count_as_our_value():
    row = V.check_our_value(
        F.draft(_THEIRS, fold=False, byline=False, footer=False),
        F.slot(), F.config())
    assert row["metrics"]["sentences"][0]["tier"] == "other"


def test_byline_and_footer_are_excluded_from_our_value_arithmetic():
    """The furniture is required boilerplate; counting it would measure the
    template rather than the piece."""
    with_furniture = V.check_our_value(
        F.draft(_OURS, _PADDING), F.slot(), F.config())["metrics"]
    without = V.check_our_value(
        F.draft(_OURS, _PADDING, byline=False, footer=False),
        F.slot(), F.config())["metrics"]
    fold_words = V.word_count(V.strip_tags(F.ABOVE_FOLD))
    assert with_furniture["total_words"] == without["total_words"] == \
        V.word_count(_OURS) + V.word_count(_PADDING) + fold_words


# ─────────────────────────────────────────────────────────────────────────────
# fact anchor
# ─────────────────────────────────────────────────────────────────────────────


def test_fact_anchor_accepts_sourced_numbers():
    row = V.check_fact_anchor(
        F.draft("The composite reads 56 and the dominant scare scores 65.7."),
        F.slot(), F.config())
    assert row["ok"] is True, row["detail"]
    assert row["metrics"]["numbers_checked"] >= 1


def test_fact_anchor_rejects_an_originated_number():
    row = V.check_fact_anchor(
        F.draft("The composite reads 56, which is 23.4% above its five-year mean."),
        F.slot(), F.config())
    assert row["ok"] is False
    assert any("23.4" in u for u in row["metrics"]["unanchored"])


def test_fact_anchor_parses_explicit_unit_spelled_numbers_and_rejects_invention():
    """``twelve percent`` cannot become an invisible numeric-origin bypass."""
    slot = F.slot(facts=[{
        "id": "revenue", "ref": "chronicle:fixture", "tier": "first_party",
        "values": [12], "text": "Revenue grew 12% in the quarter.",
        "dated": "2026-07-24", "url": None, "source_name": "fixture",
    }])
    assert V.check_fact_anchor(
        F.draft("Revenue grew twelve percent in the quarter.", fold=False), slot, F.config(),
    )["ok"] is True
    invented = V.check_fact_anchor(
        F.draft("Revenue grew thirteen percent in the quarter.", fold=False), slot, F.config(),
    )
    assert invented["ok"] is False
    assert any("thirteen percent" in value.lower()
               for value in invented["metrics"]["unanchored"])


def test_fact_anchor_allows_rounding_down_in_precision():
    """65.7 -> "66" is a correct rounding and must pass."""
    row = V.check_fact_anchor(
        F.draft("The dominant scare scores about 66 on our radar."),
        F.slot(), F.config())
    assert row["ok"] is True, row["detail"]


def test_fact_anchor_rejects_invented_precision():
    """65.7 -> "65.73" adds precision the source does not have."""
    row = V.check_fact_anchor(
        F.draft("The dominant scare scores 65.73 on our radar."),
        F.slot(), F.config())
    assert row["ok"] is False
    assert any("65.73" in u for u in row["metrics"]["unanchored"])


def test_fact_anchor_exempts_small_prose_counts_but_not_percentages():
    cfg = F.config()
    assert V.check_fact_anchor(
        F.draft("There are three reasons and two of them matter."),
        F.slot(), cfg)["ok"] is True
    assert V.check_fact_anchor(
        F.draft("It moved three percent, or 3.0% on the session."),
        F.slot(), cfg)["ok"] is False


def test_fact_anchor_does_not_split_an_iso_date_into_three_numbers():
    row = V.check_fact_anchor(
        F.draft("The reading is dated 2026-07-24 and the composite is 56."),
        F.slot(), F.config())
    assert row["ok"] is True, row["detail"]


def test_fact_anchor_rejects_a_fabricated_quotation():
    row = V.check_fact_anchor(
        F.draft('The desk wrote that "the winter contract is already lost and '
                'nobody on the floor disputes it."'),
        F.slot(), F.config())
    assert row["ok"] is False
    assert row["metrics"]["unsourced_quotes"]


def test_fact_anchor_accepts_a_quotation_lifted_from_the_source():
    quote = " ".join(F.SOURCE_DOC.split()[:14])
    row = V.check_fact_anchor(
        F.draft(f'The desk wrote: "{quote}".'),
        F.slot(facts=F.facts() + [{
            "id": "q", "ref": "research_vault:demo-report", "tier": "third_party",
            "values": [], "text": F.SOURCE_DOC, "url": None, "source_name": "desk",
        }]), F.config())
    assert not row["metrics"]["unsourced_quotes"], row["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# quote lint
# ─────────────────────────────────────────────────────────────────────────────


def test_quote_lint_caps_the_number_of_quotes():
    q = '"the winter contract is already lost and nobody disputes it"'
    row = V.check_quote_lint(F.draft(f"A {q} B {q} C {q}"), F.slot(), F.config())
    assert row["ok"] is False
    assert row["metrics"]["quotes"] == 3


def test_quote_lint_caps_quote_length():
    long_quote = " ".join(["word"] * 30)
    row = V.check_quote_lint(F.draft(f'The desk said "{long_quote}".'),
                             F.slot(), F.config())
    assert row["ok"] is False
    assert row["metrics"]["oversized"]


def test_quote_lint_ignores_short_scare_quotes():
    row = V.check_quote_lint(
        F.draft('A so-called "risk-off" session, or a "melt up" if you prefer.'),
        F.slot(), F.config())
    assert row["ok"] is True
    assert row["metrics"]["quotes"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# AI-tell lexicon + pattern rules (rev-4 house-style law)
# ─────────────────────────────────────────────────────────────────────────────


def test_every_seeded_ai_tell_phrase_fires():
    cfg = F.config()
    phrases = cfg["validators"]["ai_tell_phrases"]
    assert len(phrases) == 11, "the rev-4 seed list is exactly 11 phrases"
    for phrase in phrases:
        row = V.check_ai_tells(F.draft(f"Consider this: {phrase} in the tape."),
                               F.slot(), cfg)
        assert row["ok"] is False, f"{phrase!r} did not fire"
        assert any(phrase in h for h in row["metrics"]["hits"])


def test_paragraph_opening_moreover_is_banned():
    cfg = F.config()
    assert V.check_ai_tells(
        F.draft("Moreover, the tape did the same thing again."), F.slot(), cfg
    )["ok"] is False
    # Mid-sentence is untouched — the rule is about the paragraph OPENER.
    assert V.check_ai_tells(
        F.draft("The tape did it again; moreover, it did so quietly."),
        F.slot(), cfg)["ok"] is True


def test_not_only_but_also_is_budgeted_not_banned():
    cfg = F.config()
    one = "It was not only the level but also the speed that mattered."
    assert V.check_ai_tells(F.draft(one), F.slot(), cfg)["ok"] is True
    row = V.check_ai_tells(F.draft(one, one), F.slot(), cfg)
    assert row["ok"] is False
    assert row["metrics"]["not_only_but_also"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# imported lexicons — banned vocab, advice, cheese
# ─────────────────────────────────────────────────────────────────────────────


def test_banned_lexicon_is_imported_not_forked():
    """If someone adds a term to the marketing lane, the press lane must inherit
    it.  A copied list would keep shipping the term for months."""
    from engine.marketing import copywriter

    for term in sorted(copywriter._BANNED_VOCAB):
        row = V.check_banned_lexicon(
            F.draft(f"The chart shows {term} doing something."), F.slot(), F.config())
        assert row["ok"] is False, f"{term!r} did not fire"


def test_banned_word_boundary_terms_fire_on_the_word_only():
    cfg = F.config()
    assert V.check_banned_lexicon(
        F.draft("The regime shifted last week."), F.slot(), cfg)["ok"] is False
    assert V.check_banned_lexicon(
        F.draft("The patient kept to the regimen."), F.slot(), cfg)["ok"] is True


def test_advice_lexicon_is_sentinels_list():
    from engine.marketing import sentinel

    for phrase in sentinel._DEFAULT_LEXICON_PHRASES[:6]:
        row = V.check_advice_lexicon(
            F.draft(f"Honestly, {phrase} here."), F.slot(), F.config())
        assert row["ok"] is False, f"{phrase!r} did not fire"


def test_advice_pattern_fires_on_a_price_promise():
    row = V.check_advice_lexicon(
        F.draft("This one is going to double before the autumn."), F.slot(), F.config())
    assert row["ok"] is False
    assert row["metrics"]["hits"]


def test_cheese_test_fires_on_the_v3_lexicon():
    from engine.marketing import copywriter

    cfg = F.config()
    for phrase in copywriter._BANNED_CHEESE_SUBSTRINGS:
        assert V.check_cheese_test(
            F.draft(f"And then, {phrase}."), F.slot(), cfg)["ok"] is False
    for word in copywriter._BANNED_CHEESE_WORDS:
        assert V.check_cheese_test(
            F.draft(f"The {word} were out in force."), F.slot(), cfg)["ok"] is False


def test_cheese_words_are_word_boundary_matched():
    """"apes" must not hit "shapes" — the same semantics the marketing lane uses."""
    assert V.check_cheese_test(
        F.draft("The curve takes odd shapes when it steepens."),
        F.slot(), F.config())["ok"] is True


# ─────────────────────────────────────────────────────────────────────────────
# byline, footer, primary source
# ─────────────────────────────────────────────────────────────────────────────


def test_byline_and_footer_are_required_on_every_draft():
    cfg, slot = F.config(), F.slot()
    good = F.draft("A paragraph.")
    assert V.check_byline(good, slot, cfg)["ok"] is True
    assert V.check_footer(good, slot, cfg)["ok"] is True

    assert V.check_byline(F.draft("A paragraph.", byline=False), slot, cfg)["ok"] is False
    assert V.check_footer(F.draft("A paragraph.", footer=False), slot, cfg)["ok"] is False


def test_footer_text_must_match_the_configured_sentence():
    cfg = F.config()
    d = F.draft("A paragraph.", footer=False)
    d["body_html"] += '<p class="press-footer">Nothing here is advice, probably.</p>'
    row = V.check_footer(d, F.slot(), cfg)
    assert row["ok"] is False
    assert row["metrics"]["block"] is True and row["metrics"]["text"] is False


_EXT_URL = "https://www.bls.gov/news.release/empsit.nr0.htm"
_EXT_FOLD = (f'<p>The <a href="{_EXT_URL}">Bureau of Labor Statistics</a> '
             f'published the release on 2026-07-24.</p>')


def test_first_party_slot_needs_no_above_the_fold_source_link():
    """Every W1 slot is first-party. The receipts ARE the citation — and most
    of the estate a Brief could point at is a regwall 302."""
    row = V.check_primary_source(F.draft("A paragraph."), F.slot(), F.config())
    assert row["ok"] is True
    assert row["metrics"]["kind"] == "first_party"
    assert "receipts carried inline" in row["detail"]


def test_external_slot_must_name_and_link_its_source_above_the_fold():
    cfg, slot = F.config(), F.external_slot()
    good = F.draft("A paragraph.", fold=False)
    good["body_html"] = good["body_html"].replace(F.BYLINE_HTML,
                                                  F.BYLINE_HTML + _EXT_FOLD)
    assert V.check_primary_source(good, slot, cfg)["ok"] is True

    # Link present, but below three paragraphs of preamble — buried, not cited.
    buried = F.draft(*F.FILLER_PARAGRAPHS[:3], fold=False)
    buried["body_html"] += _EXT_FOLD
    row = V.check_primary_source(buried, slot, cfg)
    assert row["ok"] is False
    assert row["metrics"]["linked"] is False


def test_external_source_naming_requires_the_full_name_not_a_token():
    """THE DEFECT THIS CLOSES: the naming half matched any >=4-char token, so
    "Mastermind track record" was satisfied by the word "record" — a piece that
    never named its source read as compliant."""
    cfg, slot = F.config(), F.external_slot()
    d = F.draft("A paragraph.", fold=False)
    d["body_html"] = d["body_html"].replace(
        F.BYLINE_HTML,
        F.BYLINE_HTML + f'<p>The <a href="{_EXT_URL}">statistics</a> came out '
                        f'on 2026-07-24.</p>')
    row = V.check_primary_source(d, slot, cfg)
    assert row["metrics"]["linked"] is True
    assert row["metrics"]["named"] is False, "a bare token must not satisfy naming"
    assert row["ok"] is False


def test_external_source_accepts_a_configured_alias():
    cfg = F.config()
    cfg["validators"]["source_name_aliases"] = {"Bureau of Labor Statistics": ["BLS"]}
    d = F.draft("A paragraph.", fold=False)
    d["body_html"] = d["body_html"].replace(
        F.BYLINE_HTML,
        F.BYLINE_HTML + f'<p>The <a href="{_EXT_URL}">BLS</a> released it.</p>')
    assert V.check_primary_source(d, F.external_slot(), cfg)["ok"] is True


# ── public link allowlist ────────────────────────────────────────────────────


def test_a_regwall_gated_link_is_a_validator_failure():
    """Verified 2026-07-26: https://www.mastermind-x.com/radar.html answers
    302 -> /?signin=1. W1 shipped with the validator REQUIRING this link."""
    d = F.draft("A paragraph.", fold=False)
    d["body_html"] += F.GATED_LINK_HTML
    row = V.check_link_allowlist(d, F.slot(), F.config())
    assert row["ok"] is False
    assert any("radar.html" in o for o in row["metrics"]["offenders"])


@pytest.mark.parametrize("gated", [
    "/radar.html", "/macro.html", "/us_track_record.html", "/movers.html",
])
def test_every_url_w1_originally_cited_now_fails(gated):
    d = F.draft("A paragraph.", fold=False)
    d["body_html"] += f'<p>See <a href="{gated}">the page</a>.</p>'
    assert V.check_link_allowlist(d, F.slot(), F.config())["ok"] is False


def test_a_public_first_party_link_passes():
    d = F.draft("A paragraph.", fold=False)
    d["body_html"] += F.PUBLIC_LINK_HTML
    row = V.check_link_allowlist(d, F.slot(), F.config())
    assert row["ok"] is True
    assert row["metrics"]["internal_links"] == 1


def test_an_external_link_is_not_subject_to_the_allowlist():
    """The allowlist is about OUR estate. An external source is the thing the
    piece is citing."""
    d = F.draft("A paragraph.", fold=False)
    d["body_html"] += f'<p>See <a href="{_EXT_URL}">the release</a>.</p>'
    row = V.check_link_allowlist(d, F.slot(), F.config())
    assert row["ok"] is True
    assert row["metrics"]["internal_links"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# frontmatter — pre-check + the sync test that makes drift fail here
# ─────────────────────────────────────────────────────────────────────────────


def test_frontmatter_precheck_passes_a_compliant_draft():
    row = V.check_frontmatter(F.draft("A paragraph."), F.slot(), F.config(), root=_REPO)
    assert row["ok"] is True, row["detail"]
    assert 120 <= row["metrics"]["description_len"] <= 155


def test_frontmatter_precheck_rejects_a_short_description():
    row = V.check_frontmatter(
        F.draft("A paragraph.", description="Too short."),
        F.slot(), F.config(), root=_REPO)
    assert row["ok"] is False
    assert "description" in row["detail"]


def test_frontmatter_precheck_rejects_a_dated_slug():
    row = V.check_frontmatter(
        F.draft("A paragraph.", slug="2026-07-26-risk-radar"),
        F.slot(), F.config(), root=_REPO)
    assert row["ok"] is False
    assert "date prefix" in row["detail"]


def test_frontmatter_fails_closed_when_the_upstream_validator_cannot_import():
    """THE DEFECT THIS CLOSES: an ImportError used to degrade to "local checks
    only" and PASS, so a 200-character title shipped with a footnote attached.
    A validator that cannot run is not a validator that agrees with you."""
    import builtins

    real_import = builtins.__import__

    def _blocked(name, *a, **kw):
        if name == "scripts.build_free_content":
            raise ImportError("jinja2 missing")
        return real_import(name, *a, **kw)

    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(builtins, "__import__", _blocked)
        row = V.check_frontmatter(F.draft("A paragraph."), F.slot(), F.config(),
                                  root=_REPO)
    finally:
        monkey.undo()

    assert row["ok"] is False
    assert "upstream_unavailable" in row["detail"]
    assert "upstream_unavailable" in row["metrics"]["upstream"]


def test_frontmatter_limits_in_sync_with_build_free_content():
    """Behavioural sync test.

    engine.press.validators mirrors build_free_content's limits for the report's
    metrics.  If someone widens the estate contract, this fails HERE — in the
    press lane that would otherwise keep quarantining legal drafts — instead of
    surfacing three merges later as an unexplained red job.
    """
    pytest.importorskip("jinja2")
    from scripts.build_free_content import _validate

    def _probe(**over):
        fm = {"slug": "s", "family": "article", "title": "T",
              "description": "d" * V.DESC_MIN, "published": "2026-07-26",
              "updated": "2026-07-26"}
        fm.update(over)
        try:
            _validate(fm, Path("s.md"), frozenset())
            return None
        except ValueError as exc:
            return str(exc)

    assert _probe(description="d" * (V.DESC_MIN - 1)) is not None
    assert _probe(description="d" * V.DESC_MIN) is None
    assert _probe(description="d" * V.DESC_MAX) is None
    assert _probe(description="d" * (V.DESC_MAX + 1)) is not None
    assert _probe(title="T" * V.TITLE_MAX) is None
    assert _probe(title="T" * (V.TITLE_MAX + 1)) is not None
    for key in V.REQUIRED_KEYS:
        fm = {"slug": "s", "family": "article", "title": "T",
              "description": "d" * V.DESC_MIN, "published": "2026-07-26",
              "updated": "2026-07-26"}
        fm.pop(key)
        with pytest.raises(ValueError):
            _validate(fm, Path("s.md"), frozenset())


# ─────────────────────────────────────────────────────────────────────────────
# length + self-similarity
# ─────────────────────────────────────────────────────────────────────────────


def test_length_budget_is_the_desks_budget():
    short = F.draft("Three words here.", byline=False, footer=False, fold=False)
    row = V.check_length(short, F.slot(min_words=300, max_words=600), F.config())
    assert row["ok"] is False
    assert row["metrics"]["min_words"] == 300 and row["metrics"]["max_words"] == 600


def test_self_similarity_flags_a_rewrite_of_our_own_recent_post(tmp_path):
    root = tmp_path / "repo"
    blog = root / "content" / "seo" / "blog"
    blog.mkdir(parents=True)
    prior = ("The radar moved to caution and the reason it gives is the growth "
             "leg rather than the credit leg, which is a different problem than "
             "the one most desks are hedging this month.")
    (blog / "prior-note.md").write_text(
        "---\nslug: prior-note\npublished: 2026-07-25\n---\n<p>" + prior + "</p>\n",
        encoding="utf-8")

    cfg, slot = F.config(), F.slot()
    repeat = V.check_self_similarity(
        F.draft(prior, fold=False, byline=False, footer=False), slot, cfg, root=root)
    assert repeat["ok"] is False
    assert repeat["metrics"]["worst_slug"] == "prior-note"

    fresh = V.check_self_similarity(
        F.draft(F.REWRITTEN_PARAGRAPH, fold=False, byline=False, footer=False),
        slot, cfg, root=root)
    assert fresh["ok"] is True, fresh["detail"]


def test_self_similarity_compares_against_staged_siblings(tmp_path):
    """THE DEFECT THIS CLOSES: the radar only read content/seo/blog/, so the ten
    drafts of the evidence gate were never compared to EACH OTHER. Ten
    near-replicates could pass the gate one at a time — the failure the radar
    exists to catch, invisible exactly when it matters most."""
    root = F.fixture_root(tmp_path)
    body = ("<p>" + F.FILLER_PARAGRAPHS[0] + "</p><p>" + F.FILLER_PARAGRAPHS[1]
            + "</p>")
    (root / "data" / "press" / "staging" / "sibling.json").write_text(json.dumps({
        "id": "press-brief-sibling", "status": "passed", "slug": "a-staged-sibling",
        "sources": [], "seed_refs": [],
        "draft": {"title": "t", "description": "d", "slug": "a-staged-sibling",
                  "body_html": body},
    }), encoding="utf-8")

    cfg = F.config()
    replicate = F.draft(F.FILLER_PARAGRAPHS[0], F.FILLER_PARAGRAPHS[1],
                        fold=False, byline=False, footer=False)
    row = V.check_self_similarity(replicate, F.slot(), cfg, root=root)
    assert row["ok"] is False
    assert row["metrics"]["worst_slug"] == "staged:a-staged-sibling"

    fresh = F.draft(F.REWRITTEN_PARAGRAPH, fold=False, byline=False, footer=False)
    assert V.check_self_similarity(fresh, F.slot(), cfg, root=root)["ok"] is True


def test_self_similarity_does_not_compare_a_draft_to_its_own_staged_record(tmp_path):
    """A re-validated slot must not fail against the record it already wrote."""
    root = F.fixture_root(tmp_path)
    body = "<p>" + F.FILLER_PARAGRAPHS[0] + "</p>"
    (root / "data" / "press" / "staging" / "self.json").write_text(json.dumps({
        "id": "press-brief-2026-07-26-testslot01",     # == F.slot()["id"]
        "status": "passed", "slug": "same-slug", "sources": [], "seed_refs": [],
        "draft": {"title": "t", "description": "d", "slug": "same-slug",
                  "body_html": body},
    }), encoding="utf-8")
    row = V.check_self_similarity(
        F.draft(F.FILLER_PARAGRAPHS[0], fold=False, byline=False, footer=False),
        F.slot(), F.config(), root=root)
    assert row["ok"] is True
    assert row["metrics"]["peers"] == 0


def test_self_similarity_ignores_posts_outside_the_window(tmp_path):
    root = tmp_path / "repo"
    blog = root / "content" / "seo" / "blog"
    blog.mkdir(parents=True)
    prior = ("The radar moved to caution and the reason it gives is the growth "
             "leg rather than the credit leg, which is a different problem.")
    (blog / "old-note.md").write_text(
        "---\nslug: old-note\npublished: 2025-01-01\n---\n<p>" + prior + "</p>\n",
        encoding="utf-8")
    row = V.check_self_similarity(
        F.draft(prior, fold=False, byline=False, footer=False),
        F.slot(), F.config(), root=root)
    assert row["ok"] is True
    assert row["metrics"]["peers"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# the suite as a whole
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_records_every_check_pass_or_fail():
    report = V.validate(F.draft(_OURS), F.slot(), F.config(), root=_REPO)
    assert [c["name"] for c in report["checks"]] == list(V.CHECK_NAMES)
    assert len(V.CHECK_NAMES) == 17


def test_a_crashing_check_reads_as_a_failure_not_a_pass(monkeypatch):
    def _boom(*_a, **_kw):
        raise RuntimeError("detonated")

    monkeypatch.setattr(V, "check_our_value", _boom)
    monkeypatch.setattr(V, "_SUITE", tuple(
        (n, _boom if n == "our_value" else fn, r) for n, fn, r in V._SUITE))
    report = V.validate(F.draft(_OURS), F.slot(), F.config(), root=_REPO)
    assert report["ok"] is False
    assert "our_value" in report["failed"]
    row = next(c for c in report["checks"] if c["name"] == "our_value")
    assert "detonated" in row["detail"]


def test_a_fully_compliant_draft_passes_the_whole_suite():
    d = F.draft(_OURS, F.REWRITTEN_PARAGRAPH,
                "The level to watch is the composite falling under 56, because "
                "that is where our own record stops being ambiguous. Watch it; "
                "do not chase it.")
    report = V.validate(d, F.slot(), F.config(), root=_REPO)
    assert report["ok"] is True, report["failed"]
    assert report["our_value_share"] >= F.config()["validators"]["our_value_min"]
