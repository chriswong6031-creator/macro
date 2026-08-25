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

OWNER_LANE_LABELS = [
    ("Buy Now", "立即买入"),
    ("In Favour", "看好"),
    ("Bottoming Watch", "洗盘观察"),
    ("Reduce / Avoid", "减仓 / 回避"),
]


def test_lane_labels_are_the_owner_native_act_now_vocabulary():
    """The four lane labels must be the page owner's verbatim Act-Now lane
    titles (templates/canada.html.j2:854-996, `_ca_anlane(...)` title_en/
    title_zh — "Buy Now"/"In Favour"/"Bottoming Watch"/"Reduce / Avoid").

    Reverting to the composer's old invented vocabulary ("Entry now",
    "Setting up", "In favour", "Reduce / avoid" — lower-cased, paraphrased,
    and never published anywhere by the page owner) is the defect this test
    guards against: it invents a parallel lane taxonomy the owner never
    endorsed, which is exactly what a "no invented vocabulary" constitution
    forbids.
    """
    text = _composer_text()
    for en, zh in OWNER_LANE_LABELS:
        assert '"' + en + '"' in text, (
            f"owner-native lane label {en!r} missing from composer; "
            "reverting to invented labels like 'Entry now'/'Setting up' is "
            "the defect this pin exists to catch"
        )
        assert zh in text, f"owner-native lane label zh {zh!r} missing from composer"
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
    #stocktable-wrap — rather than recomputing or re-fetching anything."""
    text = _composer_text()
    assert "ca-v36-evidence" in text, "Evidence & Record section id missing"
    assert "Evidence &amp; Record" in text or "Evidence & Record" in text, (
        "Evidence & Record EN heading missing"
    )
    assert "证据与往绩" in text, "Evidence & Record ZH heading missing"
    # The move-by-reference pattern: the composer must query the legacy trk
    # chip (by class or by its #trd-btn anchor) rather than rebuild it.
    assert ('qs(".trk")' in text) or ("#trd-btn" in text), (
        "composer no longer references the legacy .trk/#trd-btn chip; "
        "Track Record must be MOVED via appendChild, never recomputed"
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
    (never a new click-handler path)."""
    text = _composer_text()
    assert "ca-v36-modal-lanes" in text, "group-action band container missing"
    assert "LANE_DEFS" in text, (
        "lane labels for the group-action band must come from the same "
        "LANE_DEFS source collectSectors() uses — never a second, "
        "independently-invented lane vocabulary"
    )
    assert "data-ca-modal-kind" in text and "data-ca-modal-id" in text
    # Group-action rows must reuse the SAME data attributes as modalRows(),
    # not a parallel activation mechanism.
    assert text.count("data-ca-modal-kind") >= 2, (
        "expected data-ca-modal-kind on both modalRows() and the new "
        "group-action lane rows"
    )
