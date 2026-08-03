"""China Prophet v2 artifact + overflow UX contract.

The former 110/overflow split was positional and mislabeled raw legacy early
warnings as names that had cleared the actionable screen.  V2 exposes disjoint
semantic lanes and keeps ``watch`` only as a compatibility union.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "templates" / "china.html.j2").read_text()


def test_artifact_contract_versions_semantic_lanes():
    from scripts.export_signal_contracts import ARTIFACT_MANIFEST

    entry = next(
        e for e in ARTIFACT_MANIFEST
        if e["artifact"] == "site/factordata/china_standouts.json"
    )
    assert entry["schema_version"] == "2.0.0"
    required = set(entry["schema_fields"])
    assert {
        "schema_version", "actionable", "board_definition",
        "execution_coverage", "lane_counts", "ranking",
        "more_actionable", "late_or_unfillable", "forming", "track_ledger",
    } <= required
    assert "watch" in (entry.get("optional_fields") or [])
    assert {"prophet", "lane", "lane_reasons", "microstructure", "adv_yi"} <= set(
        entry["schema_item_fields"]
    )


def test_flat_overflow_spam_is_gone_and_depth_is_collapsed():
    assert "Also cleared today's screen" not in TEMPLATE
    assert "beyond the board's" not in TEMPLATE
    assert 'class="cn-depth ' in TEMPLATE
    assert "<details" in TEMPLATE
    assert "Early warnings — not confirmed" in TEMPLATE
    assert "Wait / unfillable / do not chase" in TEMPLATE
    assert "legacy early/T4/null-tier observations" in TEMPLATE


def test_more_actionable_left_the_drawer_for_the_unified_grid():
    """CONTRACT CHANGE (prophet board priority engine G0.2, 2026-08-02).

    `more_actionable` used to be a collapsed "More live setups" depth drawer of compact
    rows. It is now part of the ONE score-ordered grid of full prophet cards, so the
    drawer — and the assertion that used to require it — are both gone. What replaced
    the old guarantee is stronger: those rows are no longer a second-class list at all.
    Pinned in full by tests/test_cn_board_unified_grid.py.
    """
    # Assert on the CALL SITE, not the bare phrase: the template keeps a comment naming
    # the drawer it replaced, and a source-grep suite cannot tell documented history
    # from live markup (memory `test-pins-a-string-inside-dead-code`).
    assert "{{ t('More live setups'" not in TEMPLATE
    assert "更多实时形态" not in TEMPLATE
    assert "cn_depth_grid(_more)" not in TEMPLATE
    assert '<details class="cn-depth" data-stf="entry">' not in TEMPLATE
    # the rows still exist — they are merged into the live grid, in score order
    assert "set _more_lane = setups.get('more_actionable') or []" in TEMPLATE
    assert "_mrg.append({'r': _e.r, 'f': false})" in TEMPLATE


def test_depth_rows_are_cards_not_one_wrapped_name_paragraph():
    assert 'class="cn-depth-card"' in TEMPLATE
    assert "cn_depth_grid(_late)" in TEMPLATE
    assert "cn_depth_grid(_forming)" in TEMPLATE
    # Backward fallback data is still collapsed and formatted, never deleted.
    assert "Legacy depth — classification pending" in TEMPLATE
    assert "cn_depth_grid(_legacy_depth)" in TEMPLATE


def test_live_rank_copy_names_only_earned_components():
    assert "signal 35%" in TEMPLATE
    assert "entry 25%" in TEMPLATE
    assert "runway 20%" in TEMPLATE
    assert "bottom quality 10%" in TEMPLATE
    assert "reversal-sleeve membership 10%" in TEMPLATE
    assert "not a win probability or return forecast" in TEMPLATE


def test_zero_universe_publishes_outage_instead_of_reusing_stale_board():
    source = (ROOT / "scripts" / "build_china_library.py").read_text()
    assert "published explicit empty outage artifact" in source
    assert "Scored universe collapsed to zero" in source
    assert "allow_nan=False" in source


def test_renderer_rejects_legacy_fallback_under_prophet_v2_heading():
    from scripts.build_china import (
        _is_current_prophet_artifact,
        _prophet_outage_shell,
    )

    assert not _is_current_prophet_artifact({"buy": [{"ticker": "OLD"}]})
    assert _is_current_prophet_artifact({
        "schema_version": "2.0.0",
        "board_definition": "cn_prophet_v2",
        "buy": [],
    })
    shell = _prophet_outage_shell("test failure")
    assert shell["board_definition"] == "cn_prophet_v2"
    assert shell["buy"] == []
    assert shell["data_outage"]["flag"] is True
