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


def test_group_action_band_uses_owner_lanes_and_existing_modal_activation():
    """Change 4: the Expand-leadership modal gets a group-action band above
    the two ranking panes, partitioned into the same four owner lanes, with
    rows reusing the existing data-ca-modal-kind/data-ca-modal-id activation
    (never a new click-handler path).

    The interpolation-shape assertion below kills a mutation that a bare
    `"data-ca-modal-kind" in text` check would miss: stripping the data
    attributes out of laneItemHtml() (so group-action rows silently stop
    being clickable) while leaving delegation selectors like
    `[data-ca-modal-kind][data-ca-modal-id]` and this docstring's prose
    untouched — the bare token would still be present in the file, but the
    live `data-ca-modal-kind="' + x.kind` interpolation would only appear
    once (in modalRows()) instead of twice.
    """
    text = _composer_text()
    assert "ca-v36-modal-lanes" in text, "group-action band container missing"
    assert "LANE_DEFS" in text, (
        "lane labels for the group-action band must come from the same "
        "LANE_DEFS source collectSectors() uses — never a second, "
        "independently-invented lane vocabulary"
    )
    # modalRows() and laneItemHtml() must BOTH build the same live
    # data-ca-modal-kind="' + x.kind interpolation — not just contain the
    # bare attribute name somewhere (e.g. in a delegation selector string).
    live_kind_interpolations = text.count('data-ca-modal-kind="\' + x.kind')
    assert live_kind_interpolations >= 2, (
        "expected the live `data-ca-modal-kind=\"' + x.kind` interpolation "
        "in both modalRows() and laneItemHtml() (found "
        f"{live_kind_interpolations}); group-action rows must reuse the "
        "SAME activation attributes as modalRows(), not a parallel "
        "mechanism, and stripping them from laneItemHtml() must fail this "
        "test even though the bare 'data-ca-modal-kind' token still "
        "appears elsewhere (e.g. the click-delegation selector)"
    )
    live_id_interpolations = text.count('data-ca-modal-id="\' + esc(x.id)')
    assert live_id_interpolations >= 2, (
        "expected the live `data-ca-modal-id=\"' + esc(x.id)` interpolation "
        "in both modalRows() and laneItemHtml() (found "
        f"{live_id_interpolations})"
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
