"""Byte-level pins for the Canada Stock Dashboard V3.6 client composer.

The composer (site/canada-stock-v36.js, entitled-only, no template pair) hides
grid cards and the grid container with the HTML ``hidden`` attribute
(``card.hidden = !show``).  The UA sheet's ``[hidden]{display:none}`` loses to
ANY author display rule, and both hidden targets carry one: the page stylesheet
sets ``.pvcard{display:flex}`` and the composer's own style sets
``.ca-v36-card-grid{display:grid}``.  Production consequence (found in the
2026-08-25 entitled acceptance matrix): the Top Picks segment, the leadership
filter's grid hiding, and the grid/table view switch were all visually inert —
state, counters, aria and the empty-state message updated while every card
stayed painted.  The repair scopes explicit ``[hidden]`` overrides into the
composer's injected style; these tests pin that the overrides ship and that
the hide mechanism they cover is still the one the composer uses.
"""

import re
from pathlib import Path

import pytest

COMPOSER = Path(__file__).resolve().parents[1] / "site" / "canada-stock-v36.js"

REQUIRED_HIDDEN_OVERRIDES = [
    # container: grid pane must actually vanish when the Table view is active
    ".ca-v36-card-grid[hidden]{display:none!important}",
    # cards: Top Picks segment + leadership filter hide via card.hidden
    ".ca-v36-card-grid .pvcard[hidden]{display:none!important}",
]


def _composer_text() -> str:
    if not COMPOSER.exists():
        pytest.skip("sparse checkout omits site/ (needs_full_checkout)")
    return COMPOSER.read_text(encoding="utf-8")


def test_hidden_attribute_overrides_ship_in_composer_style():
    text = _composer_text()
    for rule in REQUIRED_HIDDEN_OVERRIDES:
        assert rule in text, (
            f"composer style lost the {rule!r} override; the hidden attribute "
            "is defeated by author display rules (.pvcard{display:flex} / "
            ".ca-v36-card-grid{display:grid}) and the Top Picks segment, "
            "leadership filter and grid/table switch go visually inert"
        )


LOADER = Path(__file__).resolve().parents[1] / "templates" / "dashboard-icons.js"


def test_loader_retries_transient_entitled_fetch_failures():
    """The composer asset is entitled-only and its gate consults the auth
    backend per request; a transient 401/503 there used to strand an entitled
    visitor on the legacy page with no retry (2026-08-25 acceptance, twice in
    ~7 loads).  Pin the bounded onerror retry in the loader — both the
    template and (when checked out) the shipped site pair."""
    for path in [LOADER, LOADER.parents[1] / "site" / "dashboard-icons.js"]:
        if not path.exists():
            continue  # sparse checkout omits site/; templates/ always present
        text = path.read_text(encoding="utf-8")
        block = text[text.find("__mmCanadaStockV36Loader"):]
        assert "script.onerror" in block, f"{path.name}: loader lost its onerror retry"
        assert "attempt < 3" in block, f"{path.name}: loader retry is no longer bounded"
        assert "!window.__mmCanadaStockV36" in block, (
            f"{path.name}: retry must not re-inject after a successful mount"
        )


def test_composer_still_hides_via_hidden_attribute():
    """The overrides above only matter while the composer hides with
    ``.hidden`` / ``hidden`` attribute semantics.  If the hide mechanism ever
    migrates to classes (like the table rows' ``ca-v36-hidden``), this test
    fails to force the override list above to be re-reviewed rather than
    silently pinning dead CSS."""
    text = _composer_text()
    assert "card.hidden = !show" in text.replace("  ", " "), (
        "composer no longer hides grid cards via the hidden attribute; "
        "re-review REQUIRED_HIDDEN_OVERRIDES before deleting them"
    )


# ---------------------------------------------------------------------------
# V3.7 functional-completeness pins (SOL-STOCK-DASH-V37-CA-FUNCTIONAL-
# COMPLETENESS-20260825). Chairman review found V3.6 deleted useful
# capability (Track Record vanished, group-action intelligence removed
# instead of compressed) — "simplicity through compression, not deletion."
# These pins hold the four bounded V3.7 changes in place.
# ---------------------------------------------------------------------------

# (sel, en, zh) — the exact LANE_DEFS binding. Order matches the file so a
# swapped-lane mutation (e.g. "Buy Now" moved onto #anv2-red) is visible in
# a diff against this table too.
LANE_BINDINGS = [
    ("#anv2-buy", "Buy Now", "立即买入"),
    ("#anv2-pull", "In Favour", "看好"),
    ("#anv2-bot", "Bottoming Watch", "洗盘观察"),
    ("#anv2-red", "Reduce / Avoid", "减仓 / 回避"),
]


def test_lane_labels_are_the_owner_native_act_now_vocabulary():
    """The four lane labels must be the page owner's verbatim Act-Now lane
    titles (templates/canada.html.j2:854-996, `_ca_anlane(...)` title_en/
    title_zh — "Buy Now"/"In Favour"/"Bottoming Watch"/"Reduce / Avoid"),
    each bound to its OWN selector in LANE_DEFS — not merely present
    somewhere in the file.

    This pins the selector<->label BINDING via a regex over the literal
    LANE_DEFS entry, not bare string presence: a mutation that swaps a
    label onto the wrong lane (e.g. "Buy Now" moved from #anv2-buy onto
    #anv2-red) would still satisfy a bare `'"Buy Now"' in text` check but
    fails this one, because the regex requires sel/en/zh to appear together
    in that exact entry.

    Reverting to the composer's old invented vocabulary ("Entry now",
    "Setting up", "In favour", "Reduce / avoid" — lower-cased, paraphrased,
    and never published anywhere by the page owner) is the defect this test
    also guards against: it invents a parallel lane taxonomy the owner
    never endorsed, which is exactly what a "no invented vocabulary"
    constitution forbids.
    """
    text = _composer_text()
    for sel, en, zh in LANE_BINDINGS:
        pattern = (
            r'sel:\s*"' + re.escape(sel) + r'",\s*'
            r'en:\s*"' + re.escape(en) + r'",\s*'
            r'zh:\s*"' + re.escape(zh) + r'"'
        )
        assert re.search(pattern, text), (
            f"LANE_DEFS no longer binds {sel!r} to en={en!r} zh={zh!r} "
            "as one entry (sel/en/zh must appear together in that order); "
            "either the label was swapped onto the wrong lane, or it was "
            "moved out of LANE_DEFS into a second, independently-invented "
            "vocabulary"
        )
    # The old invented English labels must not reappear verbatim.
    for stale in ("Entry now", "Setting up"):
        assert '"' + stale + '"' not in text, (
            f"invented lane label {stale!r} reappeared in the composer; "
            "lane labels must come from templates/canada.html.j2's owner-"
            "published Act-Now lane titles, not composer-invented prose"
        )


def test_evidence_and_record_section_restores_track_record():
    """Change 3 restores Track Record (deleted in V3.6) as a compact
    'Evidence & Record' panel that MOVES the legacy `.trk`/`#trd-btn` chip
    via appendChild — the same owner-DOM-move pattern already used for
    #stocktable-wrap — rather than recomputing or re-fetching anything.

    Three mutations this pin kills that a looser check would miss:
    - deleting the `appendChild(trk)` call (section renders but stays
      empty, since nothing ever moves the chip into it) — killed by the
      literal `appendChild(trk)` assertion, not just "trk" appearing
      somewhere in the move-pattern comments;
    - renaming the section id off `ca-v36-evidence` while leaving the
      `.ca-v36-evidence-body` CSS class behind — killed by asserting the
      exact `id="ca-v36-evidence"` markup, which the CSS class text alone
      does not satisfy;
    - defining `evidenceSectionHtml()` but never splicing its call into
      `buildShell()`'s section string (section never renders even when
      `.trk` exists) — killed by requiring the function name to appear at
      least twice (its definition AND its `trk ? evidenceSectionHtml() : ''`
      call site).
    """
    text = _composer_text()
    assert 'id="ca-v36-evidence"' in text, (
        "Evidence & Record section markup missing its exact id="
        '"ca-v36-evidence" — the .ca-v36-evidence-body CSS class alone '
        "does not prove the <section> exists"
    )
    assert "Evidence &amp; Record" in text or "Evidence & Record" in text, (
        "Evidence & Record EN heading missing"
    )
    assert "证据与往绩" in text, "Evidence & Record ZH heading missing"
    assert "appendChild(trk)" in text, (
        "composer no longer moves the legacy .trk chip via appendChild(trk); "
        "Track Record must be MOVED into the section body, never recomputed "
        "or left unattached"
    )
    assert text.count("evidenceSectionHtml()") >= 2, (
        "evidenceSectionHtml() must appear at least twice: once where it is "
        "defined and once where buildShell() splices its call "
        "(`trk ? evidenceSectionHtml() : ''`) into the panel sequence — "
        "otherwise the section can be defined but never rendered"
    )
    assert "measurement.html" in text, "Methodology link to measurement.html missing"


def test_no_new_fetch_urls_and_no_track_ledger_fetch():
    """Constitution: the only two fetch URLs remain the Canada basket/pulse
    artifacts. The trd dialog fetches its own ledger itself (data-url on
    #trd-dlg, wired by _track_record_dlg.html.j2's own inline script) — the
    composer must never independently fetch factordata/ca_track_ledger.json,
    which would duplicate a fetch the owner-rendered dialog already owns."""
    text = _composer_text()
    get_json_calls = re.findall(r'getJson\("([^"]+)"\)', text)
    assert set(get_json_calls) == {
        "canadabasketdata/baskets.json",
        "canadabasketdata/sector_pulse_canada.json",
    }, f"unexpected getJson URL set: {get_json_calls!r}"
    assert "ca_track_ledger" not in text, (
        "composer must never fetch factordata/ca_track_ledger.json itself; "
        "the trd dialog owns that fetch"
    )


def test_act_now_panel_renders_at_rest_above_prophet_never_modal_only():
    """V3.8 (§13.1): the owner-lane group-action map renders AT REST above
    Prophet — never (only) inside the Expand-leadership modal. Pins (a) the
    #ca-v36-actnow section inside buildShell()'s composition BEFORE
    #ca-v36-prophet; (b) renderActNow() actually called on the mount path;
    (c) the V3.7 modal group-action band (ca-v36-modal-lanes) is GONE — the
    at-rest panel is the one home; (d) at-rest action rows reuse the SAME
    data-ca-lead-kind/-id activation the leadership rows use (one path,
    activate() only — never a parallel mechanism)."""
    text = _composer_text()
    m = re.search(r"main\.innerHTML = .*?researchToolsHtml\(\)|main\.innerHTML = .*?</section>';", text, re.S)
    assert m, "could not locate buildShell()'s main.innerHTML composition"
    shell = m.group(0)
    actnow_idx = shell.find('id="ca-v36-actnow"')
    prophet_idx = shell.find('id="ca-v36-prophet"')
    assert actnow_idx != -1, "buildShell() no longer composes #ca-v36-actnow at rest"
    assert prophet_idx != -1, "buildShell() lost the #ca-v36-prophet section"
    assert actnow_idx < prophet_idx, (
        "What to Act On Now must render ABOVE Prophet (§4 page grammar)"
    )
    assert "renderActNow()" in text.split("main.innerHTML")[1], (
        "renderActNow() is never called after the shell mounts"
    )
    assert "ca-v36-modal-lanes" not in text, (
        "the V3.7 modal group-action band is back — the at-rest panel is "
        "the one home for group action"
    )
    m2 = re.search(r"function anRowHtml\b.*?(?=\n  function )", text, re.S)
    assert m2, "could not locate anRowHtml() function body via regex"
    an_body = m2.group(0)
    assert 'data-ca-lead-kind="sector" data-ca-lead-id="\' + esc(x.id)' in an_body, (
        "at-rest action rows no longer carry the data-ca-lead-kind/-id pair "
        "— they must reuse the one existing activation path (activate() via "
        "bind()'s delegation), never a parallel click mechanism"
    )


def test_sector_rank_is_never_lane_traversal_and_theme_rank_is_owner_only():
    """DEC:V38-ACTION-IS-NOT-LEADERSHIP / architecture §8.2: the V3.7
    presentation-minted sector rank (`rank: out.length + 1`) is deleted and
    must never return; sectors carry rank: null. Themes keep ONLY the
    owner-published rank — the V3.7 `th.rank || idx + 1` sort-position
    fallback is likewise a minted number and must not return. leadRow()
    renders `Theme #N` for an owner-ranked theme and an em dash otherwise;
    no sector ever renders a number."""
    text = _composer_text()
    assert "out.length + 1" not in text, (
        "the lane-traversal sector rank (out.length + 1) is back — lane "
        "traversal is never rank"
    )
    m = re.search(r"function collectSectors\b.*?(?=\n\n|\n  function tone)", text, re.S)
    assert m, "could not locate collectSectors() function body via regex"
    # Every rank: assignment in collectSectors must be the literal null —
    # scan all occurrences rather than merely requiring one null somewhere
    # (adversarial review 2026-08-27, finding 4: the earlier disjunct form
    # was a tautology).
    rank_values = re.findall(r"rank\s*:\s*([^,]+),", m.group(0))
    assert rank_values and all(v.strip() == "null" for v in rank_values), (
        f"collectSectors() assigns rank values {rank_values!r} — sectors "
        "must always carry rank: null (no canonical sector-rank owner)"
    )
    m2 = re.search(r"function collectThemes\b.*?(?=\n\n  function )", text, re.S)
    assert m2, "could not locate collectThemes() function body via regex"
    th_body = m2.group(0)
    assert "th.rank != null ? th.rank : null" in th_body, (
        "collectThemes() no longer restricts theme rank to the owner's own "
        "value — a positional fallback (idx + 1) mints a rank the owner "
        "never published"
    )
    assert "idx + 1" not in th_body, (
        "the positional theme-rank fallback (idx + 1) is back in "
        "collectThemes()"
    )
    m3 = re.search(r"function leadRow\b.*?(?=\n  function )", text, re.S)
    assert m3, "could not locate leadRow() function body via regex"
    assert 'x.kind === "theme" && x.rank != null ? "Theme #" + x.rank : "—"' in m3.group(0), (
        "leadRow() no longer renders rank as owner-only `Theme #N` with the "
        "em-dash fallback — either sectors gained a number or the "
        "no-synthesized-rank guard was dropped"
    )
    assert "padStart" not in text, (
        "a padStart rank formatter reappeared — the bare zero-padded rank "
        "cell is the V3.7 presentation this correction removes"
    )


def test_theme_rank_language_gated_on_owner_and_prophet_count_label():
    """V3.8 §6.2/§6.3: rank language (the Theme-rank basis chip, the modal
    Rank column) renders only while an owner-ranked theme exists
    (state.hasThemeRank); the at-rest count chip is labelled Prophet/候选
    (the ambiguous BOARD label is gone everywhere) and counts render only
    when canonical membership is known — unknown membership must never
    render as zero (members stays null, count stays null, renderers branch
    on count != null)."""
    text = _composer_text()
    assert "state.hasThemeRank = themes.some(function (x) { return x.rank != null; })" in text, (
        "collectThemes() no longer derives state.hasThemeRank"
    )
    m = re.search(r"function renderLeadership\b.*?(?=\n  /\*|\n  function )", text, re.S)
    assert m, "could not locate renderLeadership() function body via regex"
    col_body = m.group(0)
    assert "state.hasThemeRank ?" in col_body and 'bi("Theme rank", "主题排名")' in col_body, (
        "the Theme-rank basis chip is missing or unconditional in "
        "renderLeadership() — a bare number without a visible basis (or a "
        "basis with no owner) is the V3.7 confusion V3.8 corrects"
    )
    assert 'bi("Board", "榜单")' not in text, (
        "the ambiguous Board/榜单 count label is back somewhere in the file"
    )
    man = re.search(r"function anRowHtml\b.*?(?=\n  function )", text, re.S)
    assert man, "could not locate anRowHtml() function body via regex"
    assert 'bi("Prophet", "候选")' in man.group(0), (
        "the at-rest count chip is no longer labelled Prophet/候选"
    )
    mo = re.search(r"function modalPane\b.*?(?=\n  function )", text, re.S)
    assert mo, "could not locate modalPane() function body via regex"
    assert "rk ? '<th>' + bi(\"Rank\", \"排名\")" in mo.group(0), (
        "the modal Rank column is unconditional again — it must render only "
        "under state.hasThemeRank"
    )
    mr = re.search(r"function modalRows\b.*?(?=\n  function )", text, re.S)
    assert mr, "could not locate modalRows() function body via regex"
    assert '"Theme #" + x.rank : "—"' in mr.group(0), (
        "modalRows() lost the owner-only Theme # rank cell"
    )
    # Membership knowledge is PER GROUP via the board's own sector
    # vocabulary — a lane name outside that vocabulary must stay null
    # (adversarial review 2026-08-27, finding 1: a global flag rendered
    # false '0 · Prophet' rows for every lane whose taxonomy differs from
    # the board's, e.g. lane 'Communication Services' vs board
    # 'Communication').
    m2 = re.search(r"function collectSectors\b.*?(?=\n\n|\n  function tone)", text, re.S)
    assert m2, "could not locate collectSectors() function body via regex"
    sec_body = m2.group(0)
    assert re.search(r"var sectorVocab = new Set\(state\.rows\.map", sec_body), (
        "collectSectors() no longer builds the board's sector vocabulary"
    )
    assert "sectorVocab.has(name.en) ? sectorMembers(name.en) : null" in sec_body, (
        "collectSectors() no longer gates membership per group on the "
        "board's own sector vocabulary — a lane name outside the board "
        "taxonomy would render a false 0 · Prophet"
    )
    assert "state.membershipKnown" not in text, (
        "the page-global membershipKnown flag is back — membership "
        "knowledge must stay per group"
    )
    for fn, snippet in [
        ("leadRow", 'x.count != null ? x.count : "—"'),
        ("modalRows", 'x.count != null ? x.count : "—"'),
        ("anRowHtml", "var countHtml = x.count != null ? '"),
    ]:
        mf = re.search(r"function " + fn + r"\b.*?(?=\n  function )", text, re.S)
        assert mf, f"could not locate {fn}() function body via regex"
        assert snippet in mf.group(0), (
            f"{fn}() no longer branches on count != null — unknown "
            "membership would render as zero, and missing ≠ zero"
        )


def test_leadership_surface_is_themes_only_no_covert_sector_ordering():
    """Adversarial review 2026-08-27, finding 2 (MAJOR) + architecture
    §8.2.4: Canada has no sector-rank owner, so the Leadership & Rotation
    surface renders THEMES ONLY — an action-ordered, truncated sector list
    would be §6.2's 'numbering rows because they happen to be rendered
    first' with the digit removed. Sectors stay fully useful through What
    to Act On Now and their group pages. Pins: renderLeadership() consumes
    state.themes and never state.sectors; the modal composes exactly one
    (theme) pane and the 'Sector Leadership' pane title is gone; the
    surviving empty copy names the THEME axis."""
    text = _composer_text()
    m = re.search(r"function renderLeadership\b.*?(?=\n  /\*|\n  function )", text, re.S)
    assert m, "could not locate renderLeadership() function body via regex"
    body = m.group(0)
    assert "state.themes.slice(0, 5)" in body, (
        "renderLeadership() no longer renders the top-5 owner-ranked themes"
    )
    assert "state.sectors" not in body, (
        "renderLeadership() consumes state.sectors again — an action-"
        "ordered sector list on the leadership surface is a covert rank"
    )
    assert "Theme ranking unavailable" in body, (
        "the leadership empty state no longer names the theme axis"
    )
    mo = re.search(r"function openModal\b.*?(?=\n  /\*|\n  function )", text, re.S)
    assert mo, "could not locate openModal() function body via regex"
    assert "state.sectors" not in mo.group(0), (
        "openModal() composes a sector pane again — no sector-rank owner "
        "means no sector leadership surface at any depth"
    )
    assert 'bi("Sector Leadership", "板块领先")' not in text, (
        "the Sector Leadership pane title is back"
    )


def test_activation_affordance_requires_canonical_membership():
    """Adversarial review 2026-08-27, findings 1+3: a group with unknown
    membership must not offer a filter at all — activating it would no-op
    allowed() and paint the whole board as if it matched. Every activation
    surface (at-rest rows, leadership rows, modal rows) renders its
    data-ca-* activation attributes ONLY when x.members is non-null; the
    unknown-membership row keeps the group-research route as its
    affordance."""
    text = _composer_text()
    for fn, gate in [
        ("anRowHtml", "var act = x.members != null ? ' data-ca-lead-kind=\"sector\" data-ca-lead-id=\"' + esc(x.id) + '\"' : ' disabled';"),
        ("leadRow", "var act = x.members != null ? ' data-ca-lead-kind=\"' + x.kind + '\" data-ca-lead-id=\"' + esc(x.id) + '\"' : ' disabled';"),
        ("modalRows", "var act = x.members != null ? ' tabindex=\"0\" data-ca-modal-kind=\"' + x.kind + '\" data-ca-modal-id=\"' + esc(x.id) + '\"' : '';"),
    ]:
        m = re.search(r"function " + fn + r"\b.*?(?=\n  function )", text, re.S)
        assert m, f"could not locate {fn}() function body via regex"
        assert gate in m.group(0), (
            f"{fn}() no longer gates its activation attributes on "
            "x.members != null — an unknown-membership group would offer a "
            "filter that no-ops and claims the full board matches"
        )


def test_at_rest_lane_rows_capped_at_three_with_view_all():
    """V3.8 §5.2 density law: ≤3 group rows per lane at rest; more only via
    the explicit View-all expansion."""
    text = _composer_text()
    assert re.search(r"var AN_AT_REST = 3;", text), (
        "AN_AT_REST is no longer exactly 3 — the at-rest density pin is broken"
    )
    m = re.search(r"function anLaneHtml\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate anLaneHtml() function body via regex"
    body = m.group(0)
    assert "items.slice(0, AN_AT_REST)" in body, (
        "anLaneHtml() no longer caps the collapsed lane at AN_AT_REST rows"
    )
    assert "items.length > AN_AT_REST" in body and "data-ca-an-view" in body, (
        "anLaneHtml() lost the View-all control or its threshold"
    )


def test_act_now_presentation_controls_never_touch_population_or_filter():
    """V3.8 §5.5: switching the visible mobile lane / expanding View all is
    presentation-only. setAnLane()/toggleAnLane() must not call setSource/
    activate/applyFilter or assign state.source/state.filter, and the
    default-lane election runs ONLY while no lane is chosen (an OR on the
    chosen lane's emptiness would hijack a user's empty-lane tap — HK
    adversarial-review finding 1)."""
    text = _composer_text()
    for fn in ("setAnLane", "toggleAnLane"):
        m = re.search(r"function " + fn + r"\b.*?\n  \}", text, re.S)
        assert m, f"could not locate {fn}() function body via regex"
        body = m.group(0)
        for forbidden in ("setSource(", "activate(", "applyFilter(",
                          "state.source", "state.filter"):
            assert forbidden not in body, (
                f"{fn}() references {forbidden!r} — Act-Now presentation "
                "controls must never mutate the Prophet population or filter"
            )
    m2 = re.search(r"function renderActNow\b.*?(?=\n  function )", text, re.S)
    assert m2, "could not locate renderActNow() function body via regex"
    body2 = m2.group(0)
    assert "if (state.anLane == null) {" in body2, (
        "renderActNow() lost the null-only default-lane election guard"
    )
    assert not re.search(r"state\.anLane == null\s*\|\|", body2), (
        "the default-lane election guard is an OR — a chosen-but-empty lane "
        "would be silently overridden on every render"
    )


def test_mobile_segment_grammar_one_lane_at_a_time():
    """V3.8 §5.5: at ~390px one segmented lane selector + ONE lane body at a
    time — never four stacked lane cards."""
    text = _composer_text()
    assert re.search(r"\.ca-v36-an-seg\{display:none", text), (
        "the Act-Now segment bar lost its desktop display:none base rule"
    )
    mq = re.search(r"@media\(max-width:680px\)\{.*?\}\"", text, re.S)
    assert mq, "could not locate the 680px media query block"
    for rule in [
        ".ca-v36-an-seg{display:flex}",
        ".ca-v36-an-lanes{grid-template-columns:1fr}",
        ".ca-v36-an-lane{display:none}",
        ".ca-v36-an-lane.is-current{display:block}",
    ]:
        assert rule in mq.group(0), (
            f"680px media query lost {rule!r} — the mobile one-lane grammar "
            "is broken"
        )


def test_known_zero_group_keeps_research_route_and_lane_order_is_owner_order():
    """V3.8 §5.4/§10: a known-zero group stays useful — at-rest rows carry
    the owner's sectors/<id>.html route and the known-zero empty state uses
    quiet copy + the route, never filter-miss language. And the at-rest
    lane order is the ACTION owner's own DOM order (laneIdx), never the
    theme/leadership axis."""
    text = _composer_text()
    m = re.search(r"function anRowHtml\b.*?(?=\n  function )", text, re.S)
    assert "x.href" in m.group(0) and "ca-v36-an-go" in m.group(0), (
        "anRowHtml() no longer renders the owner group-research route"
    )
    m2 = re.search(r"function emptyStateHtml\b.*?(?=\n  function )", text, re.S)
    assert m2, "could not locate emptyStateHtml() function body via regex"
    e_body = m2.group(0)
    assert "item.members.size === 0" in e_body, (
        "emptyStateHtml() lost its known-zero branch"
    )
    assert "No current Prophet names in this group." in e_body, (
        "the quiet §10 known-zero copy is gone"
    )
    assert "该组别暂无 Prophet 候选。" in e_body, "ZH known-zero copy is gone"
    assert "item.href" in e_body and "ca-v36-empty-go" in e_body, (
        "the known-zero state no longer offers the group-research route"
    )
    assert "laneIdx: out.length" in text, (
        "collectSectors() no longer stamps the action owner's row order"
    )
    m3 = re.search(r"function anLaneItems\b.*?(?=\n  function )", text, re.S)
    assert re.search(r"a\.laneIdx \|\| 0\) - \(b\.laneIdx \|\| 0", m3.group(0)), (
        "anLaneItems() no longer sorts by laneIdx — the leadership axis "
        "would order/gate the action surface"
    )


def test_fresh_cue_lives_in_prophet_header_and_is_absent_when_zero():
    """The absorbed Leading Now strip's one surviving datum — the owner
    .pv-mk-new fresh-signal count — renders in the Prophet header (it
    describes Prophet cards) and is absent when zero; the strip itself
    (ca-v36-leading) must not return."""
    text = _composer_text()
    assert "ca-v36-leading" not in text, (
        "the standalone Leading Now strip is back — V3.8 absorbs it (§4)"
    )
    m = re.search(r"function renderFresh\b.*?(?=\n\n)", text, re.S)
    assert m, "could not locate renderFresh() function body via regex"
    body = m.group(0)
    assert "pv-mk-new" in body, (
        "renderFresh() no longer counts the owner's .pv-mk-new markers"
    )
    assert "host.hidden = !fresh" in body, (
        "renderFresh() no longer hides the cue at zero — an empty "
        "placeholder is forbidden"
    )
    assert 'id="ca-v36-fresh"' in text, (
        "the Prophet-header fresh-cue slot is gone from buildShell() markup"
    )


def test_leadership_activation_never_force_switches_population():
    """Sol adversarial gate (2026-08-25): "Leadership filters can reduce
    either population without silently switching modes" and "selecting a
    group/action with zero matching Top Picks must show an explicit zero
    state such as 'No Top Picks in this group'; it must never silently
    switch to All Candidates; if All Candidates contains records, preserve
    the empty Top Picks state and invite the user to switch population
    deliberately."

    activate() must set state.filter and re-render via applyFilter() only
    — it must NOT force state.source to "all" (the V3.6-inherited defect:
    clicking any leadership row silently left Top Picks for All
    Candidates, so the reader never saw that their filter emptied the
    board they were looking at). The negative assertion is scoped to
    activate()'s own function body (extracted via a regex capture between
    `function activate` and the next `function `) rather than the whole
    file, so the deliberate, user-initiated `setSource("all")` call wired
    to the .ca-v36-empty-switch button in bind() does not false-positive
    this pin — only activate() forcing the switch as a side effect is
    forbidden.
    """
    text = _composer_text()
    m = re.search(r"function activate\b.*?(?=\n  function )", text, re.S)
    assert m, "could not locate activate() function body via regex"
    body = m.group(0)
    assert "setSource(" not in body, (
        "activate() calls setSource(...), which force-switches the Top "
        "Picks / All Candidates population as a side effect of leadership "
        "activation; the Sol gate forbids this — only a deliberate user "
        'action (the .ca-v36-empty-switch button) may call setSource("all")'
    )
    assert 'state.source = "all"' not in body, (
        'activate() directly sets state.source = "all"; leadership '
        "activation must leave the active population untouched"
    )
    assert "applyFilter()" in body, (
        "activate() must re-render via applyFilter() after setting "
        "state.filter, now that setSource() (which used to trigger the "
        "re-render as a side effect) is no longer called here"
    )
    # The zero-state invitation must exist as a deliberate, separately
    # clicked control — never a silent mode switch.
    assert "No Top Picks in this group." in text, "EN zero-state invitation missing"
    assert "该组别中暂无首选。" in text, "ZH zero-state invitation missing"
    assert "ca-v36-empty-switch" in text, "deliberate switch-to-All button missing"
