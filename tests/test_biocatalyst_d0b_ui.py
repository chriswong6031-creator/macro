"""BC-D0b — the premium trial product: stance, two clocks, and bilingual parity.

These are source-level contract tests over the shipped browser assets. They
exist because the BC-D0a reference pack was rejected on four named defects
(`research/BIOCATALYST_D0A_DESIGN_ADJUDICATION_2026-08-06.md` §2), and a later
visual refactor must not be able to reintroduce any of them quietly:

* D1 — a ZH surface carrying raw English field names and state enums.
* D2 — a surface that shows state and never answers "so what do I do".
* D3 — a constant reprinted on every row instead of once in the footer.
* D4 — a graphic with no axis, no units, and no stated reading.
* D5 — the five evidence cues occupying the widest Tier-1 band as a grid.
"""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
PLATES = ROOT / "mockups" / "refs" / "biocatalyst" / "d0b"

JS = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
CSS = (TEMPLATES / "biocatalyst.css").read_text(encoding="utf-8")
PAGE = (TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")

CJK = re.compile(r"[㐀-鿿豈-﫿　-〿＀-￯]")

# The only Latin-script runs a ZH-locale string may carry (ruling §3.3): the
# source's own proper nouns, a registry identifier, an ISO-8601 stamp, a unit,
# and a version token. Everything else must be native Chinese.
ZH_LATIN_ALLOWLIST = (
    r"ClinicalTrials\.gov",
    r"BioCatalyst Intelligence",
    r"FDA",
    r"NCT(?:\d{8})?",
    r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?Z?)?",
    r"UTC",
    r"[vV]\d+",
)

# The six research stances minted by the ruling §2/D2. No other stance
# vocabulary is legal on this product, and none of them is a market call.
RESEARCH_STANCES = {
    "read": ("Read the record", "记录可直接看"),
    "check": ("Check the source", "去核对来源"),
    "wait": ("Wait for the record", "等记录更新"),
    "reconcile": ("Reconcile the conflict", "两处对不上"),
    "historical": ("Treat as historical", "这是当时的记录"),
    "none": ("Nothing here", "暂无内容"),
}

# The twelve-rank deterministic precedence of
# research/BIOCATALYST_D0A_IA_STATE_CONTENT_CONTRACT.md §4, adopted verbatim.
STATE_PRECEDENCE = [
    ("locked", 1),
    ("integrity_block", 2),
    ("source_capability_absent", 3),
    ("ambiguous_identity", 4),
    ("contradiction", 5),
    ("correction", 6),
    ("source_outage", 7),
    ("stale", 8),
    ("historical", 9),
    ("partial", 10),
    ("empty", 11),
    ("normal", 12),
]


def _render() -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    return env.get_template("biocatalyst.html.j2").render(
        generated_utc="2026-08-02T12:00:00Z",
        active_section="research",
        active_page="biocatalyst",
    )


def _latin_residue(text: str) -> list[str]:
    residue = text
    for pattern in ZH_LATIN_ALLOWLIST:
        residue = re.sub(pattern, " ", residue)
    return re.findall(r"[A-Za-z]+", residue)


def _zh_strings() -> list[tuple[str, str]]:
    """Every Chinese string this page can put in front of a reader."""

    found: list[tuple[str, str]] = []
    for literal in re.findall(r"'((?:[^'\\]|\\.)*)'", JS):
        if CJK.search(literal):
            found.append(("biocatalyst.js", literal))
    for literal in re.findall(r'<span class="l-zh">([^<]*)</span>', PAGE):
        if CJK.search(literal):
            found.append(("biocatalyst.html.j2", literal))
    for literal in re.findall(r'data-(?:label|placeholder|rest)-zh="([^"]*)"', PAGE):
        if CJK.search(literal):
            found.append(("biocatalyst.html.j2", literal))
    for literal in re.findall(r"t\('[^']*',\s*'([^']*)'\)", PAGE):
        if CJK.search(literal):
            found.append(("biocatalyst.html.j2", literal))
    return found


def _stance_table() -> dict[str, tuple[str, str]]:
    block = JS[JS.index("var RESEARCH_STANCE = {") : JS.index("var STATE_STANCE = {")]
    return {
        key: (english, chinese)
        for key, english, chinese in re.findall(
            r"(\w+): \['([^']*)', '([^']*)',", block
        )
    }


def _decision_reasons() -> list[tuple[str, str, str]]:
    return re.findall(
        r"noteState\(list, '([a-z_]+)', knownAt, '([^']*)', '([^']*)'\)", JS
    )


# --------------------------------------------------------------------------- #
# D1 — the bilingual gate. This is the one the reference pack failed outright.
# --------------------------------------------------------------------------- #


def test_zh_copy_carries_no_unwhitelisted_latin_run():
    """A ZH string may hold a proper noun, an ID, a stamp, a unit — nothing else.

    The rejected D0a pack shipped `状态 / CHANGE TAPE CORRECTION` and four
    untranslated English field names inside Chinese chrome. That is not a
    translation bug: it is a ZH surface that was designed in English. This gate
    fails on the first Latin word that is not on the allowlist above.
    """

    offenders = [
        (source, literal, _latin_residue(literal))
        for source, literal in _zh_strings()
        if _latin_residue(literal)
    ]
    assert not offenders, (
        "ZH copy must be native product copy, never a raw English token drop: "
        + "; ".join(f"{src}: {lit!r} leaks {run}" for src, lit, run in offenders)
    )


def test_the_bilingual_gate_actually_inspects_this_product_s_zh_copy():
    """A gate that scans nothing passes everything."""

    strings = _zh_strings()
    assert len(strings) > 150
    assert any("记录可直接看" == literal for _, literal in strings)
    assert any("方案对照" == literal for _, literal in strings)
    # Native ZH names the object before the qualifier and drops the copula, so
    # these are authored phrases rather than word-for-word English.
    assert any("不在记录中" == literal for _, literal in strings)
    assert any("尚未核对" == literal for _, literal in strings)


def test_no_translated_text_lands_in_a_title_attribute():
    html = _render()
    for match in re.findall(r'title="([^"]*)"', html):
        assert not CJK.search(match), match


# --------------------------------------------------------------------------- #
# D2 — the Decision Sentence.
# --------------------------------------------------------------------------- #


def test_decision_sentence_speaks_only_the_six_research_stances():
    table = _stance_table()
    assert {key: (en, zh) for key, (en, zh) in table.items()} == RESEARCH_STANCES

    # Every one of the twelve states resolves to one of the six, so a surface
    # can never render a state with no stance attached to it.
    mapping = re.findall(r"(\w+): '(\w+)'", JS[JS.index("var STATE_STANCE = {") : JS.index("var CHANGE_KIND_CATALOG")])
    assert {code for code, _ in mapping} == {code for code, _ in STATE_PRECEDENCE}
    assert {stance for _, stance in mapping} <= set(RESEARCH_STANCES)
    # All six are reachable; a vocabulary with dead entries is a vocabulary of
    # fewer than six.
    assert {stance for _, stance in mapping} == set(RESEARCH_STANCES)


def test_decision_sentence_stays_inside_its_word_budget():
    """<=14 words EN and <=24 characters ZH, stance included."""

    table = _stance_table()
    for code, english, chinese in _decision_reasons():
        stance_key = re.search(rf"\b{code}: '(\w+)'", JS)
        assert stance_key, code
        stance_en, stance_zh = table[stance_key.group(1)]
        sentence_en = f"{stance_en} — {english}"
        sentence_zh = f"{stance_zh}{chinese}"
        assert len(sentence_en.split()) <= 14, sentence_en
        assert len(sentence_zh) <= 24, sentence_zh


def test_decision_sentence_never_carries_a_signal_word_or_a_falsifier():
    """Banned inside the sentence: signals, scores, state codes, refutation.

    The operator ruling of 2026-07-27 keeps falsifier language off every
    front-facing surface; tripwires keep evaluating out of sight.
    """

    banned = (
        "signal", "score", "rank", "forecast", "probability", "falsifier",
        "refuted", "证伪", "materiality", "catalyst",
    )
    for code, english, chinese in _decision_reasons():
        for word in banned:
            assert word not in english.lower(), (code, english)
            assert word not in chinese, (code, chinese)
        # No internal state enum leaks into the reason itself.
        assert code not in english
        assert "_" not in english


def test_the_decision_sentence_ships_even_when_the_answer_is_nothing():
    assert "'empty', knownAt, 'nothing matches what you asked for.'" in JS
    assert "'locked', knownAt, 'this view needs full access.'" in JS
    assert "if (!list.length) noteState(list, 'normal'" in JS
    # It is painted before the first payload lands and on every terminal state,
    # so no surface can render with a blank stance.
    assert "writeUrl(); paintFrame();" in JS
    for painter in ("paintLockedWorkspace", "paintUnavailableWorkspace", "renderQueue"):
        body = JS[JS.index(f"function {painter}(") :]
        assert "paintFrame();" in body[: body.index("\n  }") + 6]


def test_decision_sentence_is_the_first_thing_in_the_main_pane():
    html = _render()
    assert html.index('id="bci-decision"') < html.index('id="bci-braid"')
    assert html.index('id="bci-decision"') < html.index('id="bci-queue"')
    assert html.index('id="bci-queue-title"') < html.index('id="bci-decision"')


# --------------------------------------------------------------------------- #
# The twelve-rank precedence table.
# --------------------------------------------------------------------------- #


def test_state_precedence_is_the_twelve_rank_table_verbatim():
    block = JS[JS.index("var STATE_PRECEDENCE = [") : JS.index("var RESEARCH_STANCE")]
    parsed = [(code, int(rank)) for code, rank in re.findall(r"\['(\w+)', (\d+)\]", block)]
    assert parsed == STATE_PRECEDENCE


def test_state_precedence_tie_break_is_earliest_known_at_then_lexical_code():
    body = JS[JS.index("function resolveStates()") : JS.index("function paintDecision()")]
    assert "left.rank - right.rank" in body
    assert "left.known_at < right.known_at" in body
    assert "left.code < right.code" in body
    # Every rank in the table has a trigger, so the renderer can reach all of
    # locked, partial, unavailable, stale, correction, outage, empty,
    # historical, and ambiguity.
    triggered = {code for code, _, _ in _decision_reasons()}
    assert triggered == {code for code, _ in STATE_PRECEDENCE}


def test_secondary_states_are_named_once_in_the_footer_not_on_every_row():
    """D3: a constant belongs in the footer, once."""

    assert "states.slice(1).map(stateLabel)" in JS
    assert "function paintPanelFoot()" in JS
    assert 'ui.panelFoot.appendChild(el(\'b\', \'\', tr(\'One page, one receipt. \'' in JS
    # The row renderers must not reprint the panel-wide caveats.
    row = JS[JS.index("function makeChangeRow(") : JS.index("function screenText(")]
    assert "no trade call" not in row.lower()
    assert "research context" not in row.lower()
    assert "registry edit is not" not in row.lower()


def test_a_trial_name_is_not_reprinted_down_its_own_run_of_tape_rows():
    row = JS[JS.index("function makeChangeRow(") : JS.index("function screenText(")]
    assert "if (!index || nctOf(valueAt(state.rows[index - 1], 'trial')) !== id)" in row


def test_the_five_cues_sit_inline_at_tier_one_not_in_a_label_value_grid():
    """D5: Tier 1 shows meaning; the structured grid stays on Tier 2."""

    assert ".bci-cues { display: flex;" in CSS
    row = JS[JS.index("function makeScreenRow(") : JS.index("function recordStateLabel(") if JS.index("function recordStateLabel(") > JS.index("function makeScreenRow(") else len(JS)]
    body = JS[JS.index("function makeScreenRow(") :]
    body = body[: body.index("\n  function ")]
    assert "bci-cues" in body
    assert "bci-detail-grid" not in body
    # Precision moves to the dossier rather than the glance row.
    assert "function locatorSection(fieldEvidence)" in JS
    assert "Where each field comes from" in JS


# --------------------------------------------------------------------------- #
# D4 — the Temporal Braid, the signature element.
# --------------------------------------------------------------------------- #


def test_braid_renders_two_tracks_on_one_labelled_scale():
    html = _render()
    assert 'class="bci-braid-rail is-effective"' in html
    assert 'class="bci-braid-rail is-known"' in html
    assert 'id="bci-braid-scale"' in html
    assert 'id="bci-braid-unit"' in html
    # The scale carries units and real dates, not bare bars.
    assert "ui.braidScale.appendChild(el('span', '', timestampLabel(isoDay(low + span * fraction))))" in JS
    assert "days across " in JS
    assert " 天 · " in JS


def test_braid_connector_length_is_the_reporting_lag_and_says_so_in_words():
    body = JS[JS.index("function paintBraid()") : JS.index("function pad(value, width)")]
    assert "var left = (record.posted - low) / span * 100" in body
    assert "right = (record.known - low) / span * 100" in body
    assert "mark.style.width = Math.max(end - start, 0.6) + '%'" in body
    # Stated in the panel footer, once.
    assert "Each bar is the gap between the two clocks" in JS
    assert "横杠越长" in JS
    assert JS.count("Each bar is the gap between the two clocks") == 1


def test_braid_corrections_branch_and_never_replace_the_original_mark():
    body = JS[JS.index("function paintBraid()") : JS.index("function pad(value, width)")]
    assert "if (record.corrected) {" in body
    assert "bci-braid-branch" in body
    assert "bci-braid-corr" in body
    # The original recorded mark is appended before the branch and is never
    # removed, which is the visual form of the append-only law.
    assert body.index("bci-braid-known") < body.index("bci-braid-branch")
    assert "removeChild" not in body[body.index("if (record.corrected)") :]


def test_braid_is_readable_with_motion_off_and_reachable_from_the_keyboard():
    assert ".bci-braid-rec, .bci-facet, .bci-chip-drop, .bci-cohort-run, .bci-peer-src { transition: none !important; }" in CSS
    # No braid geometry is animated at all, so nothing lives in the motion.
    braid_css = CSS[CSS.index(".bci-braid {") : CSS.index(".bci-chips {")]
    assert "animation" not in braid_css
    assert "transition" not in braid_css
    body = JS[JS.index("function paintBraid()") : JS.index("function pad(value, width)")]
    assert "var mark = el('button', 'bci-braid-rec'" in body
    assert "mark.setAttribute('aria-label', braidPhrase(record))" in body
    # Every mark also has a plain-text equivalent in the DOM, so the reading
    # never depends on hovering (`no_hover_only_meaning`).
    assert "ui.braidList.appendChild(line)" in body
    assert "aria-live=\"polite\"" in _render()


def test_braid_replaces_the_meaningless_source_timeline_bars():
    assert "Source timeline" not in JS
    assert "bci-source-timeline" not in CSS


# --------------------------------------------------------------------------- #
# Trial Screen.
# --------------------------------------------------------------------------- #


def test_trial_screen_preserves_the_api_s_literal_filter_semantics():
    assert "clean(valueAt(query, 'filter_composition')) !== 'literal_and'" in JS
    assert "clean(valueAt(query, 'primary_completion_matching')) !== 'full_interval_containment'" in JS
    assert "clean(payload.sort_order) !== 'primary_completion_interval_ascending_then_nct_id'" in JS
    # No client-side widening, canonicalisation, or fuzzy retrieval: the browser
    # sends the literal filter values and rejects a page bound to other ones.
    assert "function screenQueryMatchesCurrentFilters(query)" in JS
    assert "Trial screen query binding mismatch" in JS
    for fuzzy in ("fuzzy", "levenshtein", "synonym", ".sort(", "toLowerCase().includes"):
        assert fuzzy not in JS[JS.index("function screenParams()") : JS.index("function parseCohort(")]


def test_trial_screen_pagination_is_generation_bound_and_offset_checked():
    assert "if (pagination.offset !== loadedBefore) throw new Error('Invalid trial screen offset')" in JS
    assert "Trial screen total changed during pagination" in JS
    assert "Repeated trial screen cursor" in JS
    assert "Incomplete trial screen pagination" in JS
    # A generation change mid-page restarts the query rather than stitching two
    # data cuts together, and says so in plain words.
    assert "if (append && state.generation && incomingGeneration !== state.generation)" in JS
    assert "The registry page changed. Reloading the selected filters." in JS
    assert "登记页面已变化。正在重新加载所选筛选条件。" in JS


def test_active_query_is_a_removable_chip_set_not_a_dense_form_echo():
    assert "function activeChips()" in JS
    assert "function dropChip(key)" in JS
    assert "tr('Remove filter: ', '移除筛选：')" in JS
    assert ".bci-chip-drop" in CSS
    assert "No filter set — showing everything the register covers." in JS


def test_facet_counts_disclose_missingness_and_what_they_cannot_mean():
    assert "MISSINGNESS_STATES = ['observed', 'source_null', 'source_missing', 'not_applicable', 'parser_degraded', 'license_restricted']" in JS
    # Both grammatical numbers ship. A single absent trial must read "1 trial does
    # not record this field.", never "1 trials do not record this field." — the
    # count is data-driven, so the singular branch is reachable in production.
    assert "' trial does not record '" in JS
    assert "' trials do not record '" in JS
    assert "' trial could not be read'" in JS
    assert "' trials could not be read'" in JS
    assert "' for this field.'" in JS
    # Self-excluding, unique-trial counting is stated rather than implied, so a
    # reader never reads the buckets as an additive breakdown.
    assert "so they do not add up to the total" in JS
    assert "不会与总数相加吻合" in JS
    assert "clean(valueAt(semantics, 'filter_composition')) !== 'literal_and_self_excluding_dimension'" in JS


# --------------------------------------------------------------------------- #
# Peer Matrix.
# --------------------------------------------------------------------------- #


def test_peer_matrix_resolves_only_the_cohort_the_user_typed():
    assert "PEER_MIN_COHORT = 2" in JS
    assert "PEER_MAX_COHORT = 100" in JS
    assert "function parseCohort(raw)" in JS
    assert "Peer cohort binding mismatch" in JS
    assert "Peer row outside the requested cohort" in JS
    assert "cohort.join('|') !== state.cohort.slice().sort().join('|')" in JS
    # A single trial is a dossier, not a comparison.
    assert "List at least two trials to compare." in JS


def test_peer_matrix_never_discovers_ranks_or_links_a_trial_to_a_security():
    body = JS[JS.index("function peerFieldValue(row, name)") : JS.index("function renderQueue()")]
    for forbidden in ("ticker", "issuer", "security", "competitor", "best", "score", "rank", "similar"):
        assert forbidden not in body.lower(), forbidden
    assert "never discovers peers" in JS or "never finds peers for you" in JS
    assert "不会发现同类试验" in JS
    assert "不会把试验关联到公司或证券" in JS


def test_peer_matrix_keeps_identity_frozen_wide_and_uses_cards_when_narrow():
    assert ".bci-peer .bci-peer-id { position: sticky; left: 0;" in CSS
    assert ".bci-peer thead th { position: sticky; top: 0;" in CSS
    assert "var narrow = window.matchMedia('(max-width: 760px)').matches" in JS
    assert "bci-peer-cards" in JS
    assert ".bci-peer-card" in CSS
    # Switching between the two forms is re-rendered, not hidden with CSS, so a
    # phone never receives a squeezed desktop table.
    assert "state.peerNarrow !== window.matchMedia('(max-width: 760px)').matches" in JS
    assert "The comparison continues to the right" in JS


def test_peer_cells_show_coverage_and_reach_the_evidence_thread():
    assert "coverage === 'covered' ? 'is-covered' : (coverage === 'partial' ? 'is-partial' : 'is-uncovered')" in JS
    assert ".bci-peer-cell.is-partial .bci-peer-val" in CSS
    assert ".bci-peer-cell.is-uncovered { background: repeating-linear-gradient" in CSS
    assert ".bci-peer-legend" in CSS
    # Coverage is not carried by colour alone: partial is dashed, uncovered is
    # hatched and italic, and all three are named in a legend.
    assert "On the record" in JS and "Partly on the record" in JS and "Not on the record" in JS
    # Every cell carries its own source locator and opens the evidence thread.
    assert "state.evidenceCell = { field: name, locator: locator }" in JS
    assert "function locatorTail(locator)" in JS
    assert "SOURCE_LOCATOR = /^\\/protocolSection\\/[A-Za-z]+\\/[A-Za-z]+$/" in JS
    assert "open the evidence thread at " in JS


def test_the_exact_source_locator_survives_as_the_signature_receipt():
    """The frozen §1.3 idea: a literal JSON pointer into the source record."""

    assert "function validFieldEvidence(evidence)" in JS
    assert "source_field_locators" in JS
    assert "Each line is the exact place in the source record this value was read from." in JS
    assert "每一行都是该值在来源记录中的确切读取位置。" in JS
    assert "function historyVersionUrl(id, version)" in JS


# --------------------------------------------------------------------------- #
# Authority, honesty, and the two themes.
# --------------------------------------------------------------------------- #


def test_the_authority_ceiling_is_checked_on_every_page_this_lane_added():
    assert "AUTHORITY_MUST_FORBID = ['originate_signal', 'rank_security', 'select_security', 'size_position', 'gate_decision', 'execute_trade', 'raise_authority']" in JS
    assert "clean(ceiling) !== 'A1_EXPLAIN'" in JS
    for envelope in (
        "Invalid trial screen authority contract",
        "Invalid facet authority contract",
        "Invalid peer set authority contract",
    ):
        assert envelope in JS
    assert "validCeilingAuthority(valueAt(item, 'authority'))" in JS


def test_no_front_facing_falsifier_or_validated_language():
    for source in (JS, CSS, PAGE):
        lowered = source.lower()
        for banned in ("falsifier", "refuted", "证伪", "validated", "probability", "forecast"):
            assert banned not in lowered, banned


def test_light_is_a_composed_theme_not_an_inverted_dark_one():
    light = CSS[CSS.index('html[data-theme="light"] {') : CSS.index("body.bci-page {")]
    for token in ("--bci-stamp:", "--bci-filed:", "--bci-redline:", "--bci-line:", "--bci-shadow:"):
        assert token in light
    # Panel-on-canvas depth: white cards on a deeper desk tone, not panel≈bg.
    assert 'html[data-theme="light"] body.bci-page { background: var(--bci-ruled), #e8ebf1; }' in CSS
    # Every dark-first idiom this lane introduced carries a light counterpart.
    assert 'html[data-theme="light"] .bci-stamp-mark' in CSS
    assert 'html[data-theme="light"] .bci-stamp-mark.is-wait' in CSS
    assert 'html[data-theme="light"] .bci-stamp-mark.is-conflict' in CSS


def test_the_palette_is_derived_from_the_record_not_from_a_dashboard_default():
    """Ruling D6: not near-black + one teal, not warm cream + serif."""

    assert "--bci-stamp: #8f7bff" in CSS
    assert "--bci-filed: #e3a14a" in CSS
    assert "--bci-redline: #ef6a52" in CSS
    # The old single-teal accent is gone; the legacy name now resolves to the
    # stamp ink so there is exactly one accent on the page.
    assert "--bci-cyan: var(--bci-stamp)" in CSS
    assert "#20bfd3" not in CSS
    assert "#68e2ec" not in CSS
    # Mono is for figures, identifiers and pointers — never for running words.
    assert ".bci-stamp-mark {" in CSS
    stamp = CSS[CSS.index(".bci-stamp-mark {") : CSS.index("html[data-theme=\"light\"] .bci-stamp-mark {")]
    assert "font-family: var(--font-mono);" in stamp


def test_the_shell_still_ships_no_trial_data():
    html = _render()
    assert re.search(r"\bNCT\d{8}\b", html) is None
    for forbidden in ('"trials"', '"nct_id"', "field_evidence", "change_tape", "source_field_locators"):
        assert forbidden not in html


# --------------------------------------------------------------------------- #
# Browser-captured reference plates.
# --------------------------------------------------------------------------- #


def test_browser_plates_cover_every_required_viewport_theme_and_language():
    required = {
        f"d0b_{viewport}_{theme}_{language}_{surface}.png"
        for viewport, surface in (("desktop", "screen"), ("tablet", "peers"), ("mobile", "tape"))
        for theme in ("dark", "light")
        for language in ("en", "zh")
    }
    present = {path.name for path in PLATES.glob("*.png")}
    assert required <= present, sorted(required - present)
    for name in sorted(required):
        assert (PLATES / name).stat().st_size > 20_000, name
