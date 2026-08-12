"""BC-2: structural non-claims MASK IN PLACE, and site/prophet/*.json is in scope.

THE INCIDENT (2026-08-11). The anonymous landing page shipped an unearned bilingual
claim pair — "… is below its long-term trend — validated drawdown gate: size down …" /
"…已跌破长期趋势 — 已验证的回撤门槛：减小仓位。" — LIVE on templates/index.html and
site/index.html, with BC-2 reading green the whole time.

Two independent blindnesses had to line up, and this file pins both:

  1. `_STRUCTURAL` was a set of WHOLE-LINE kills. The entry
     `"(?:absolute_trend_gate|weighting|timing|note)"\\s*:.*validated` matched a `"note":`
     key ANYWHERE on a line, and the landing page bakes its showcase slice into one
     ~23,000-character `<script id="ph-data">` JSON island. One structural match therefore
     suppressed every claim in the entire island. The rule now MASKS the structural span
     in place (the _TP_CUT sentinel) instead of dropping the line, exactly as the
     2026-07-29 `_IDENT_MASK` narrowing did for CSS selectors and for the same reason:
     "Whole-line suppression was half the reason the old rule was invisible."

  2. `SCAN_GLOBS` reached `site/prophet/plans` only, so `site/prophet/showcase.json` —
     the artifact the landing island is baked FROM, carrying four fossilised board
     cautions — was never scanned at all. The glob is now `site/prophet` (scan() walks
     with rglob), and templates/*.html is scanned so the hand-authored landing SOURCE is
     gated beside its render.

Everything here goes through the REAL gate (`scan_text`), never a re-implementation, so
the tests fail if the production code path moves. Cases 1 and 6 are the mutation proof:
both PASS against this commit's guard and FAIL against the guard on origin/main.
"""
from __future__ import annotations

from scripts.check_validated_claims import SCAN_GLOBS, scan_text

# No allowlist: these fixtures assert what the gate SEES, not what the estate has earned.
# An empty allowlist means any affirmative token that survives masking is a finding.
NO_ALLOW: list[dict] = []

LANDING = "site/index.html"

# The island's real shape: a one-line application/json payload whose sibling keys include
# `note` — the key whose old whole-line rule did the suppressing.
_ISLAND = (
    '<script type="application/json" id="ph-data">'
    '{{"schema":"prophet.showcase/v2","kind":"delayed_winners","as_of":"2026-07-01",'
    '"note":"Delayed teaser — the live board is a paid product.",'
    '"cards":[{{"tk":"ABC","validated":false,"flags":[["{en}","{zh}"]]}}]}}'
    "</script>"
)
_CLAIM_EN = ("Narrative basket is below its long-term trend \\u2014 validated drawdown "
             "gate: size down.")
_CLAIM_ZH = "已跌破长期趋势 — 已验证的回撤门槛：减小仓位。"
_HONEST_EN = ("Narrative basket is below its long-term trend \\u2014 measured drawdown "
              "gate: size down.")
_HONEST_ZH = "已跌破长期趋势 — 实测回撤门槛：减小仓位。"


def test_note_key_no_longer_hides_the_whole_json_island() -> None:
    """THE INCIDENT. A `"note":` key beside the claims must not suppress them.

    Fails against origin/main's guard, where the line-100 `note` alternation killed the
    line: both halves of the live bilingual pair went unreported.
    """
    found, _ = scan_text(LANDING, _ISLAND.format(en=_CLAIM_EN, zh=_CLAIM_ZH), NO_ALLOW)
    assert len(found) >= 2, (
        "the EN and ZH halves of the landing-island claim must BOTH be reported; "
        f"got {len(found)}: {found}")
    assert all(f["file"] == LANDING and f["line_no"] == 1 for f in found)


def test_the_same_island_with_honest_copy_is_clean() -> None:
    """The fix is the COPY, not a suppression: measured/实测 wording yields nothing."""
    found, _ = scan_text(LANDING, _ISLAND.format(en=_HONEST_EN, zh=_HONEST_ZH), NO_ALLOW)
    assert found == []


# Structural shapes that must STILL be suppressed — the masks kept every genuine
# non-claim the whole-line rules were protecting. One per line, as they appear in the
# tree, so a regression names the shape it broke.
STRUCTURAL_LINES = [
    ('"tier":"validated"', 'engine-stamped scoring tier value'),
    ('"verdict":"validated"', 'engine-stamped tripwire verdict value'),
    ('{"validated": true, "n": 4}', 'a boolean data field, not a claim'),
    ('"absolute_trend_gate":"validated_risk_control — sized on the gate"',
     'engine gate-status enum value (covered by the validated_risk_control mask)'),
    ('"weighting":"state-only (no validated pathway)"',
     'passes as a NEGATED use — "no" directly precedes the token'),
    ('  .val-chip.validated { color: var(--ok); }', 'CSS class selector'),
    ('{%- if x.validated %}', 'dotted attribute access'),
    ('"criterion":"artifact validated==true ⇔ n_eff≥40 per cell"',
     'the artifact field read as an equality inside a pre-registered criterion'),
]


def test_structural_shapes_are_still_not_claims() -> None:
    for line, why in STRUCTURAL_LINES:
        found, _ = scan_text("site/x.html", line, NO_ALLOW)
        assert found == [], f"{why}: {line!r} must not be a claim, got {found}"


def test_i18n_lexicon_pair_masks_through_the_closing_bracket() -> None:
    """The widened bracket-spanning mask (templates/stockview.js:41 + its site/ twin).

    A mask that stopped at 'Validated' would excise the EN half of the label pair and
    leave the ZH half (",'已验证']") exposed as a bare affirmative token — a FALSE
    POSITIVE the whole-line skip never had. Two pairs share the real line, so both must
    be masked independently.
    """
    line = ("      'event-edge': ['Validated edge', '已验证优势'], "
            "'validated': ['Validated edge', '已验证优势'],")
    found, _ = scan_text("templates/stockview.js", line, NO_ALLOW)
    assert found == [], f"i18n label pairs must stay structural, got {found}"


def test_a_mask_does_not_hide_prose_sharing_its_line() -> None:
    """The whole point of masking: siblings on the line stay visible.

    Under origin/main's guard the `"tier":"validated"` field killed the line and the
    blurb beside it was invisible.
    """
    line = '{"tier":"validated","blurb":"a validated selection edge"}'
    found, _ = scan_text("site/x.html", line, NO_ALLOW)
    assert len(found) == 1, f"expected exactly the blurb to fire, got {found}"
    assert "selection edge" in found[0]["text"]


def test_prophet_json_tree_is_in_scan_scope() -> None:
    """COVERAGE PIN. showcase.json sat outside the old 'site/prophet/plans' root.

    scan() walks each glob root with rglob, so pinning the ROOT pins plans/, states/,
    index.json and showcase.json at once. Fails against origin/main's SCAN_GLOBS.
    """
    assert ("site/prophet", ("*.json",)) in SCAN_GLOBS, (
        "site/prophet must be the scan root — 'site/prophet/plans' leaves showcase.json, "
        f"index.json and states/ unscanned; got {SCAN_GLOBS}")

    found, _ = scan_text(
        "site/prophet/showcase.json",
        '      "Narrative basket is deteriorating — validated risk gate: trim.",',
        NO_ALLOW)
    assert len(found) == 1, f"a claim in showcase.json must be reported, got {found}"


def test_landing_source_template_is_in_scan_scope() -> None:
    """templates/index.html is the hand-authored landing SOURCE, not a Jinja template.

    It shipped the breach as a plain-copy pair with site/index.html and was unscanned
    because SCAN_GLOBS only reached templates/*.j2 and *.js.
    """
    assert "*.html" in dict(SCAN_GLOBS)["templates"], (
        f"templates/*.html must be scanned; got {dict(SCAN_GLOBS)['templates']}")
