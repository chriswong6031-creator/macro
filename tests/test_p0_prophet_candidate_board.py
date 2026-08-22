"""P0 production hotfix (GitHub #6185 / Linear MAS-111) — restores the
candidate population (`us_standouts.buy`) as a first-class, always-reachable
view of the US Prophet board on us_stocks.html, behind a Candidates|Plans
source toggle, without disturbing the migrated plan-book grid PR #6076
introduced.

One test group per production defect named in the commissioning packet:
  A  — source toggle (data-prophet-src default, #us-src-toggle presence)
  B  — DOM containers: #us-cand-grid carries neither data-mp1-grid nor
       data-provboard; #us-life-grid keeps data-mp1-grid="1"; the two grids
       share no ancestor; the gated grid holds exactly `preview_rows` real
       cards, all drawn from the input buy preview slice; the `_su`-absent
       path renders a typed Candidates-unavailable state.
  C1 — no `&lt;b&gt;` anywhere in the rendered document (the t()+|safe
       double-escape regression).
  C2 — `_cand_total` reconciles to `gate.total`; the stage shelves (plus a
       residual "Other" shelf when a stage-less row exists) sum EXACTLY to
       it — built against a fixture that would fail under the old
       `+ _ran_rows` arithmetic.
  C3 — #us-board-sub carries neither "setups" nor the "shown ·" clause.
  C4 — theme.js/site theme.js compute a heading-excluding record count;
       _us_board_cards.html.j2 marks both heading kinds `data-sm-heading`.
  D  — hydrate() reads payload.cards_html into #us-cand-grid via
       mergeBoardCards and never stamps data-mp1-grid on the fresh element.

Reuses templates/dashboard.html.j2's exact render shape and fixtures from
tests/test_dashboard_template_render.py (`_env`, `_base_vm`, `_board_row`,
`_prophet_book`) and the `_split_us_board` tier-gate helper from
scripts/build_site.py, exactly like tests/test_p_mp1_shell_repair_round.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.build_site as bs  # noqa: E402
from tests.test_dashboard_template_render import (  # noqa: E402
    _env, _base_vm, _board_row, _prophet_book,
)


def _stage_rows(n_by_stage: dict, extra_stageless: int = 0) -> list:
    """Candidate rows spanning the five recognized stages, plus optional
    rows carrying a stage value OUTSIDE `_stage_order` — the C2 residual
    "Other" shelf fixture needs at least one of those to exercise honestly."""
    rows = []
    i = 0
    for stage, n in n_by_stage.items():
        for _ in range(n):
            rows.append(_board_row(ticker=f"CAND{i}", name=f"Candidate {i}",
                                    stage=stage, lane=None))
            i += 1
    for _ in range(extra_stageless):
        rows.append(_board_row(ticker=f"CAND{i}", name=f"Candidate {i}",
                                stage="unrecognized_future_stage", lane=None))
        i += 1
    return rows


def _render_stocks(vm_overrides: dict) -> str:
    vm = _base_vm()
    vm.setdefault("gate", None)
    vm.setdefault("pgate", None)
    vm.setdefault("life_gate", None)
    vm.update(vm_overrides)
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


def _gated_render(n_by_stage: dict, extra_stageless: int = 0, preview_rows: int = 3,
                   ran_extra: int = 0):
    """One gated render exercising the full C2 arithmetic: `ran_extra` rows
    land in the SEPARATE `us_standouts.ran` array (its own section/tier
    gate) — under the pre-fix `_cand_total = gate.total + _ran_rows|length`
    this would inflate the total past what the five (or six) shelves sum
    to. Returns (html, gate, shell_su)."""
    rows = _stage_rows(n_by_stage, extra_stageless)
    us_standouts = {"buy": rows, "ran": [{"ticker": f"RAN{i}"} for i in range(ran_extra)],
                     "eligible": len(rows)}
    shell_su, gate, _locked = bs._split_us_board(us_standouts, preview_rows, gated=True)
    html = _render_stocks({"us_standouts": shell_su, "gate": gate,
                            "us_prophet_book": _prophet_book(plans=[])})
    return html, gate, shell_su


# ═══════════════════════════ A — source toggle ════════════════════════════

def test_a_data_prophet_src_defaults_candidates_when_su_present():
    rows = _stage_rows({"live": 2})
    html = _render_stocks({
        "us_standouts": {"buy": rows, "ran": [], "eligible": len(rows)},
        "us_prophet_book": _prophet_book(),
    })
    assert 'data-prophet-src="candidates"' in html
    assert 'id="us-src-toggle"' in html
    assert 'data-src="candidates"' in html and 'data-src="plans"' in html


def test_a_toggle_stays_reachable_and_typed_unavailable_state_shows_when_su_missing():
    # The toggle is deliberately UNCONDITIONAL (not gated on `_su`): the page
    # opens on Plans when `_su` is falsy, but Candidates must stay reachable
    # so the typed unavailable state (B5) is not baked-and-unreachable dead
    # markup — the A3 CSS rule that hides #us-candidates in Plans mode would
    # otherwise combine with a `_su`-gated toggle to make that state
    # permanently unseeable.
    html = _render_stocks({
        "us_standouts": None,
        "action_board": {"hold": [], "avoid": [], "notable": [{"ticker": "X"}], "buy": []},
    })
    assert 'data-prophet-src="plans"' in html
    assert 'id="us-src-toggle"' in html, (
        "the source toggle must stay reachable even when the page opens on "
        "Plans, or the typed Candidates-unavailable state can never be seen")
    assert 'id="us-src-btn-plan" type="button" aria-selected="true"' in html, (
        "the baked aria-selected state must agree with the baked "
        "data-prophet-src default")
    idx = html.find('id="us-candidates"')
    assert idx != -1
    block = html[idx:idx + 1200]
    assert 'class="mx-empty"' in block and 'class="mx-empty-why"' in block, (
        "switching to Candidates via the (now reachable) toggle must land on "
        "the typed unavailable state, not nothing")


# ═══════════════════════ B — DOM containers / cross-hydration ═════════════

def test_b_cand_grid_carries_neither_mp1_nor_provboard_marker():
    html, gate, _su = _gated_render({"live": 5})
    m = re.search(r'<div class="nbgrid"[^>]*id="us-cand-grid"[^>]*>', html)
    assert m, "expected a baked #us-cand-grid element"
    tag = m.group(0)
    assert 'data-mp1-grid' not in tag, (
        "the candidate grid must never carry the plan grid's W-L1 "
        "neutralization marker — doing so would make the repaint selector "
        "skip it too")
    assert 'data-provboard' not in tag


def test_b_life_grid_still_carries_mp1_marker_and_grids_share_no_ancestor():
    rows = _stage_rows({"live": 3})
    html, gate, _su = _gated_render({"live": 3})
    # Need real plan cards for #us-life-grid to render at all (empty plans
    # bakes the .mx-empty state instead) — re-render with a populated book.
    us_standouts = {"buy": rows, "ran": [], "eligible": len(rows)}
    shell_su, gate2, _locked = bs._split_us_board(us_standouts, 3, gated=True)
    html = _render_stocks({"us_standouts": shell_su, "gate": gate2,
                            "us_prophet_book": _prophet_book()})
    life_tag = re.search(r'<div class="nbgrid"[^>]*id="us-life-grid"[^>]*>', html)
    assert life_tag and 'data-mp1-grid="1"' in life_tag.group(0)

    plan_start = html.find('<div id="us-plan-block">')
    cand_start = html.find('id="us-cand-grid"')
    assert plan_start != -1 and cand_start != -1
    assert plan_start < cand_start, "#us-plan-block must open before #us-cand-grid"

    # #us-plan-block must CLOSE before #us-cand-grid opens — i.e. no shared
    # ancestor below .nb-grid-section (invariant E2). Walk div balance.
    segment = html[plan_start:cand_start]
    depth = 0
    close_pos = None
    for dm in re.finditer(r'<div\b|</div>', segment):
        depth += 1 if dm.group(0) == '<div' else -1
        if depth == 0:
            close_pos = dm.end()
            break
    assert close_pos is not None, "#us-plan-block never closes before #us-cand-grid"


def test_b_gated_grid_holds_exactly_preview_rows_real_cards_from_the_input_slice():
    preview_rows = 3
    rows = [_board_row(ticker=f"CAND{i}", name=f"Candidate {i}", stage="live", lane=None)
            for i in range(10)]
    us_standouts = {"buy": rows, "ran": [], "eligible": len(rows)}
    shell_su, gate, _locked = bs._split_us_board(us_standouts, preview_rows, gated=True)
    assert gate["preview"] == preview_rows
    html = _render_stocks({"us_standouts": shell_su, "gate": gate,
                            "us_prophet_book": _prophet_book(plans=[])})
    grid_start = html.find('id="us-cand-grid"')
    wall_start = html.find('id="us-tier-wall"', grid_start)
    assert wall_start != -1
    grid_html = html[grid_start:wall_start]
    assert grid_html.count('class="pvcard') == preview_rows, (
        "the tier boundary must never widen — the shell only carries the "
        "gate-sliced preview, and this grid renders _render_list.items built "
        "from that same slice")
    preview_tickers = {r["ticker"] for r in shell_su["buy"]}
    assert preview_tickers == {"CAND0", "CAND1", "CAND2"}
    for tk in preview_tickers:
        assert tk in grid_html
    # none of the withheld rows may appear
    for i in range(preview_rows, 10):
        assert f"CAND{i}" not in grid_html


def test_b_su_absent_renders_typed_unavailable_state_with_mx_empty_why():
    html = _render_stocks({
        "us_standouts": None,
        "action_board": {"hold": [], "avoid": [], "notable": [{"ticker": "X"}], "buy": []},
    })
    idx = html.find('id="us-candidates"')
    assert idx != -1, "Candidates must never be silently absent"
    block = html[idx:idx + 1200]
    assert 'class="mx-empty"' in block
    assert 'class="mx-empty-why"' in block, (
        "theme.css requires .mx-empty-why alongside .mx-empty (S4 idiom) — "
        "the unavailable state must follow the same house pattern")
    assert "hasn't published" in block or "尚未发布" in block
    assert "Plans view below is unaffected" in block or "下方的计划视图不受影响" in block


# ══════════════════════════════ C1 — escaped <b> ═══════════════════════════

def test_c1_no_escaped_b_tag_anywhere_in_the_rendered_document():
    html, gate, _su = _gated_render({"live": 5, "setting_up": 3, "ran": 2, "basing": 1,
                                      "blocked": 4})
    assert "&lt;b&gt;" not in html, (
        "t()+|safe on a string already containing raw <b>/</b> double-escapes "
        "under autoescape — the fix writes the bilingual twin explicitly")
    assert f"<b>{gate['total']}</b> screened tonight" in html


# ═══════════════════════════ C2 — census reconciliation ════════════════════

def test_c2_cand_total_equals_gate_total_not_inflated_by_the_ran_array():
    # 22 + 24 + (17-12=5 in buy) + 6 + 3 = 60 = gate.total. A separate 17-row
    # `ran` array sits alongside — under the OLD `+ _ran_rows|length`
    # arithmetic this would have inflated _cand_total to 77.
    html, gate, _su = _gated_render(
        {"live": 22, "setting_up": 24, "ran": 5, "basing": 6, "blocked": 3},
        ran_extra=17)
    assert gate["total"] == 60
    assert f"<b>{gate['total']}</b> screened tonight" in html
    assert "<b>77</b> screened tonight" not in html


def test_c2_five_shelves_sum_exactly_to_cand_total_no_residual_when_clean():
    html, gate, _su = _gated_render(
        {"live": 22, "setting_up": 24, "ran": 5, "basing": 6, "blocked": 3},
        ran_extra=17)
    figs = [int(m) for m in re.findall(r'class="fig">(\d+)</b>', html.split('class="cand-shelves"')[1].split('</div>')[0])]
    assert sum(figs) == gate["total"] == 60
    assert "us-cand-shelf-other" not in html, (
        "no residual shelf when every row carries a recognized stage")


def test_c2_residual_other_shelf_appears_only_when_a_stageless_row_exists():
    html, gate, _su = _gated_render(
        {"live": 2, "setting_up": 2, "ran": 1, "basing": 1, "blocked": 1},
        extra_stageless=4)
    assert gate["total"] == 11
    shelves_block = html.split('class="cand-shelves"')[1].split('</div>')[0]
    figs = [int(m) for m in re.findall(r'class="fig">(\d+)</b>', shelves_block)]
    assert sum(figs) == gate["total"] == 11
    assert "us-cand-shelf-other" in html
    assert '<b class="fig">4</b>' in shelves_block


# ═══════════════════════════ C3 — mixed-unit board-sub ═════════════════════

def test_c3_board_sub_drops_setups_and_shown_clause():
    rows = _stage_rows({"live": 2})
    html = _render_stocks({
        "us_standouts": {"buy": rows, "ran": [], "eligible": 76},
        "us_prophet_book": _prophet_book(plans=[]),
    })
    idx = html.find('id="us-board-sub"')
    assert idx != -1
    sub_html = html[idx:idx + 600]
    assert "setups" not in sub_html
    assert "shown ·" not in sub_html
    assert "76" not in sub_html
    assert "green dot = entry open" in sub_html or "绿点＝现在可入场" in sub_html


# ═══════════════════════ C4 — record-count contract ════════════════════════

def test_c4_us_board_cards_marks_both_heading_kinds():
    src = (ROOT / "templates" / "_us_board_cards.html.j2").read_text()
    assert 'class="nb-stage-hd' in src and 'data-sm-heading="1"' in src
    stage_hd_line = [l for l in src.splitlines() if 'nb-stage-hd sg-' in l][0]
    lane_hd_line = [l for l in src.splitlines() if 'class="nb-lane-hd"' in l][0]
    assert 'data-sm-heading="1"' in stage_hd_line
    assert 'data-sm-heading="1"' in lane_hd_line


def test_c4_theme_js_computes_heading_excluding_record_count():
    src = (ROOT / "templates" / "theme.js").read_text()
    assert "function isHd(el)" in src
    assert "data-sm-heading" in src
    assert "recTotal" in src and "recShown" in src
    # paging must still walk every child (a row stays a row)
    assert "bar.style.display = (total <= pageSize())" in src


def test_c4c_show_more_and_show_all_labels_use_record_units_not_child_units():
    src = (ROOT / "templates" / "theme.js").read_text()
    # the old child-unit constructions must be gone — replaced by record-unit
    # equivalents (nextRecs / recTotal) so "Show N more" / "Show all N" never
    # disagree with the "Showing X of Y" record count beside them
    assert "'Show ' + next + ' more'" not in src
    assert "'Show all ' + total" not in src
    assert "nextRecs" in src and "'Show ' + nextRecs + ' more'" in src
    assert "'Show all ' + recTotal" in src


def test_c4_site_theme_js_matches_template_byte_for_byte():
    a = (ROOT / "templates" / "theme.js").read_text()
    b = (ROOT / "site" / "theme.js").read_text()
    # theme.js is a specially-handled paired asset (baked Supabase config +
    # bundled Terminal overlay) — compare the SHARED prefix up to the point
    # site/theme.js's own bake divergence begins, which is exactly what
    # scripts/check_template_site_sync.py's token-split fallback does.
    assert a.splitlines()[0] == b.splitlines()[0]
    # The isHd/recTotal contract this PR adds must appear verbatim on both
    # sides — that's the part a stale `site/theme.js` would be missing.
    for needle in ("function isHd(el)", "recTotal", "recShown"):
        assert needle in a and needle in b, (
            f"{needle!r} must appear in both templates/theme.js and "
            f"site/theme.js — run scripts.check_template_site_sync --fix")


# ══════════════════════════ D — hydration wiring ════════════════════════════

def test_d_hydrate_reads_cards_html_via_mergeboardcards_never_sets_mp1_grid():
    html, gate, _su = _gated_render({"live": 5})
    hydrate_start = html.find("function hydrate(payload)")
    assert hydrate_start != -1
    teardown_start = html.find("function _pvcTeardown", hydrate_start)
    # hydrate() body — bounded loosely by the next top-level function
    next_fn = html.find("function recountStageChips", hydrate_start)
    body = html[hydrate_start:next_fn if next_fn != -1 else hydrate_start + 6000]
    assert "payload.cards_html" in body
    assert "mergeBoardCards(freshCand, payload.cards_html)" in body
    assert "getElementById('us-cand-grid')" in body
    assert "freshCand.setAttribute('data-mp1-grid'" not in body, (
        "the plan grid's W-L1 neutralization marker must never travel onto "
        "the freshly-hydrated candidate grid")
    assert "getElementById('us-tier-wall')" in body, (
        "hydrate() teardown must remove the restored candidate wall by its "
        "own id (D3)")


# ═══════════ E — the render's dead-reference guard (render 32585314359) ═══════
def test_e_no_js_assignment_impersonates_an_href_or_src_attribute():
    """The first P0 merge rendered fine and then died at the render's
    `guard — no dead site references` step, on a target named `candidates`
    "linked by" us_stocks.html. There was no such link: the source-toggle
    script assigned a string to a variable whose name is one of the two
    attribute names scripts/check_site_asset_refs.py scans for, and the
    guard's lookbehind only rejects a preceding word character or hyphen
    (which is what makes `data-` prefixed attributes safe) — an assignment
    preceded by a space is not rejected. The site never published.

    Imports the checker's OWN pattern rather than restating it, so the pin
    follows the guard if the guard moves. Asserts against the RENDERED page,
    because a comment inside a <script> ships in the bytes exactly like markup
    does — the first attempt at this fix re-introduced the failure inside the
    comment explaining it.
    """
    from scripts.check_site_asset_refs import _ATTR_RE

    html, _gate, _su = _gated_render({"live": 3, "setting_up": 2})
    targets = [m.group(1) for m in _ATTR_RE.finditer(html)]
    bogus = sorted({t for t in targets if t in ("candidates", "plans")})
    assert not bogus, (
        "the rendered page carries href/src reference(s) to "
        f"{bogus} — no such file exists, so the render's dead-reference guard "
        "fails and nothing publishes. A JS variable named href or src, or a "
        "comment spelling one followed by = and a quoted string, is enough to "
        "cause this."
    )


def test_e_source_toggle_carries_no_data_tip_so_a_mobile_tap_reaches_the_button():
    """theme.js's lens binds SEL = '[data-tip-en], .lens-q, .lens-term' and opens
    on `focusin`. A tap on a <button> inside a tipped wrapper focuses it, focusin
    bubbles to the wrapper, the lens sheet opens mid-tap, and its .lens-scrim
    receives the mouseup — so the click retargets to <body> and the button's own
    handler never runs. Measured on the deployed page at 390x844 with touch
    emulation: with the attributes the tap did nothing; without them it toggled
    both ways.

    The lens does carve out interactive controls nested inside a tip container,
    but only in its CLICK handler — which never fires, because no click survives
    the scrim. So the carve-out cannot save a focusable control here.

    NOTE: #us-st-view-toggle (Grid/Table, W8-R6) still carries data-tip-* and is
    broken on mobile the same way. That is pre-existing and deliberately NOT
    changed here — #6185 scopes this slice tightly — but it is why this test
    asserts on #us-src-toggle by id rather than on every .st-view-toggle.
    """
    html, _gate, _su = _gated_render({"live": 3})
    idx = html.find('id="us-src-toggle"')
    assert idx != -1
    open_tag = html[html.rfind("<span", 0, idx): html.find(">", idx) + 1]
    assert "data-tip-en" not in open_tag and "data-tip-zh" not in open_tag, (
        "the source toggle must not be a lens trigger: a data-tip on this wrapper "
        "makes every tap on its buttons open the tooltip sheet instead of "
        "switching the view, on every touch device.\n" + open_tag
    )
