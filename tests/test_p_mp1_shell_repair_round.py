"""P-MP1-SHELL repair round (PR #6076 adversarial review) — one test per
finding in the commissioning packet: B2 (Candidates rows ungated), B3 (false
"screened tonight" total), B4 (false "carries no plan yet" claim), S1 (gate
config fail-open on the plan-book path), S2 (candidate join built off the
sliced board), S3 (hydrate blind-appends into an already-initialized
show-more grid; no dense-view cap), S4 (missing .mx-empty-why), S5 (watch
key-absence ZH string not the ratified one), S6 (episode chip "of N" / raw
ISO date), S7 (wall copy counts plan rows but says "names"), S8 (preview
slice can include a default-hidden resolved row), S9 (zero-match ladder
filter renders silently blank), N3 (stale #us-tier-wall id).

Reuses templates/dashboard.html.j2's exact render shape and fixtures from
tests/test_dashboard_template_render.py (`_env`, `_base_vm`, `_board_row`,
`_prophet_book`, `_prophet_plan`) rather than re-deriving them — see that
module's own docstring for why the environment must mirror
scripts/build_site.py exactly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

import scripts.build_site as bs  # noqa: E402
from tests.test_dashboard_template_render import (  # noqa: E402
    _env, _base_vm, _board_row, _prophet_book, _prophet_plan,
)


# The hydrate()/GATE/LIFE_GATE script block is itself gated
# `{% if gate or pgate or life_gate %}` — several findings below live inside
# it, so those tests need at least one of the three truthy to reach it.
_DUMMY_GATE = {"tier": "essential", "payload": "/premiumdata/us_stocks.json",
               "preview": 1, "locked": 1, "total": 2, "stage_counts": {}}


def _render_stocks(vm_overrides: dict) -> str:
    vm = _base_vm()
    # gate/pgate/life_gate default to Undefined in _base_vm() — fine while all
    # three stay absent (`{% if gate or pgate or life_gate %}` short-circuits
    # on Undefined without touching `| tojson`), but the moment ANY of the
    # three is set truthy that block renders and `{{ gate | tojson }}` needs a
    # real value for the other two, not Undefined (TypeError: not JSON
    # serializable). Every caller here that sets one of the three gets real
    # None defaults for the others unless it overrides them itself.
    vm.setdefault("gate", None)
    vm.setdefault("pgate", None)
    vm.setdefault("life_gate", None)
    vm.update(vm_overrides)
    return _env().get_template("dashboard.html.j2").render(**vm, mode="stocks")


def _stage_rows(n_by_stage: dict) -> list:
    rows = []
    i = 0
    for stage, n in n_by_stage.items():
        for _ in range(n):
            rows.append(_board_row(ticker=f"CAND{i}", name=f"Candidate {i}",
                                    stage=stage, lane=None))
            i += 1
    return rows


# ─────────────────────────── B2 — Candidates rows ungated ─────────────────

def test_b2_cand_row_wired_into_tier_preview_groups():
    src = (ROOT / "templates" / "tier_preview.js").read_text()
    assert '#us-candidates .cand-rows' in src, (
        "groups() must add the Candidates shelf so the standing tier cap binds on it")
    assert ".cand-row" in src.split("function groups()")[0].split("function directRows(root)")[1], (
        "directRows() must accept .cand-row as a capped row class")


def test_b2_cand_row_class_is_unique_to_the_us_board():
    hits = []
    for f in (ROOT / "templates").glob("*.html.j2"):
        if ".cand-row" in f.read_text():
            hits.append(f.name)
    assert hits == ["dashboard.html.j2"], (
        f"widening tier_preview.js's selector list is only safe if no other page "
        f"carries .cand-row — found it in: {hits}")


def test_b2_site_copy_matches_template_copy():
    a = (ROOT / "templates" / "tier_preview.js").read_text()
    b = (ROOT / "site" / "tier_preview.js").read_text()
    assert a == b, "paired plain-copy asset drifted — run check_template_site_sync --fix"


# ─────────────────────────── B3 — false "screened tonight" total ──────────

def test_b3_candidates_total_quotes_gate_total_not_the_sliced_board():
    rows = _stage_rows({"live": 2, "setting_up": 2, "ran": 2, "basing": 1, "blocked": 3})
    us_standouts = {"buy": rows, "ran": [], "eligible": len(rows)}
    shell_su, gate, _locked = bs._split_us_board(us_standouts, 3, gated=True)
    assert gate is not None and gate["total"] == 10
    html = _render_stocks({"us_standouts": shell_su, "gate": gate,
                            "us_prophet_book": _prophet_book(plans=[])})
    assert "10</b> screened tonight" in html, (
        "the gated shell's own board sub-header already quotes gate.total for the "
        "identical honest-total problem — the Candidates total must match, not "
        "the 3-row preview slice")
    assert "3</b> screened tonight" not in html


def test_b3_candidate_shelf_pills_use_gate_stage_counts_when_gated():
    rows = _stage_rows({"live": 2, "setting_up": 2, "ran": 2, "basing": 1, "blocked": 3})
    us_standouts = {"buy": rows, "ran": [], "eligible": len(rows)}
    shell_su, gate, _locked = bs._split_us_board(us_standouts, 3, gated=True)
    html = _render_stocks({"us_standouts": shell_su, "gate": gate,
                            "us_prophet_book": _prophet_book(plans=[])})
    # The full-board truth for "live" is 2; the 3-row preview slice (live, live,
    # setting_up) would also say 2 by coincidence, so assert on "blocked" (3 true,
    # but 0 present in the first 3 preview rows) to actually distinguish the fix.
    assert '<b class="fig">3</b>' in html and "Blocked" in html.split('<b class="fig">3</b>')[1][:40], (
        "the Blocked shelf pill must read the true full-board count (3) — the "
        "preview slice contains none of them, so the old _board-derived count "
        "would have rendered 0 or omitted the pill entirely")


def test_b3_gate_note_disclosure_restored_only_when_gated():
    rows = _stage_rows({"live": 5})
    us_standouts = {"buy": rows, "ran": [], "eligible": len(rows)}
    shell_su, gate, _locked = bs._split_us_board(us_standouts, 3, gated=True)
    gated_html = _render_stocks({"us_standouts": shell_su, "gate": gate,
                                  "us_prophet_book": _prophet_book(plans=[])})
    ungated_html = _render_stocks({"us_standouts": us_standouts, "gate": None,
                                    "us_prophet_book": _prophet_book(plans=[])})
    assert 'id="us-gate-note"' in gated_html
    assert 'id="us-gate-note"' not in ungated_html


# ─────────────────────────── B4 — false "carries no plan yet" claim ───────

def test_b4_no_plan_sample_honest_when_pool_reaches_sample_size():
    full_buy = [{"ticker": f"T{i}"} for i in range(10)]
    plan_tickers = {"T0", "T1"}  # pool = 8 tickers without a plan, >= 6
    out = bs._us_candidate_no_plan_sample(full_buy, plan_tickers, sample_size=6)
    assert out["all_no_plan"] is True
    assert len(out["sample"]) == 6
    assert all(r["ticker"] not in plan_tickers for r in out["sample"])


def test_b4_no_plan_sample_fallback_flags_dishonest_claim():
    full_buy = [{"ticker": f"T{i}"} for i in range(10)]
    # Every one of the first 6 board rows carries a plan -> the honest pool is
    # empty, so the fallback sample is ALL plan-carrying, and the flag must say so.
    plan_tickers = {"T0", "T1", "T2", "T3", "T4", "T5"}
    out = bs._us_candidate_no_plan_sample(full_buy, plan_tickers, sample_size=6)
    assert out["all_no_plan"] is False
    assert len(out["sample"]) == 6


def test_b4_reproduces_the_finding_full_board_not_the_gated_slice():
    """The reported repro: a gated build's 3-row preview slice can never reach
    the 6-row sample size, so the OLD template-side computation (pool built
    from `_board`) always fell into the dishonest fallback. Computing off the
    FULL board must recover the honest branch even though the SHELL board is
    only 3 rows."""
    full_buy = [{"ticker": f"T{i}"} for i in range(20)]
    plan_tickers = {f"T{i}" for i in range(3)}  # only the preview-3 have plans
    out = bs._us_candidate_no_plan_sample(full_buy, plan_tickers, sample_size=6)
    assert out["all_no_plan"] is True, (
        "against the full 20-name board, 17 names carry no plan — comfortably "
        "past the 6-row sample size, so the honest branch must fire")


def test_r2_no_plan_sample_default_is_the_real_preview_cap_not_six():
    """Repair round 2, finding R2: the round-1 fix baked up to SIX real
    candidate rows into the anonymous-public document, relying on
    tier_preview.js's CLIENT-SIDE cap to hide the rest — exactly what
    config/site_access.yml's own law forbids ("a client-side hide is a
    marketing wall, not a gate"; view-source still reads them). Pre-migration
    and pre-repair both baked exactly 3 (the real `preview_rows`). The
    function's own default must match that — never a bare 6 — independent of
    what any call site remembers to pass."""
    full_buy = [{"ticker": f"T{i}"} for i in range(10)]
    out = bs._us_candidate_no_plan_sample(full_buy, set())
    assert len(out["sample"]) == 3, (
        f"default sample_size leaked {len(out['sample'])} rows — must default "
        "to the real tier-boundary preview cap (3), not a larger constant")


def test_r2_gated_render_bakes_exactly_preview_rows_cand_row_elements():
    """The end-to-end regression: a gated build's rendered HTML must never
    contain more than `gate.preview` real `.cand-row` elements, however
    `cand_no_plan` was computed — tier_preview.js's client-side cap is a UX
    funnel on top of this, never a substitute for it."""
    full_buy = [_board_row(ticker=f"CAND{i}", name=f"Candidate {i}", stage=None,
                            lane=None) for i in range(20)]
    # Every candidate has no plan, so the honest branch fires — the leak this
    # finding is about is specifically the SAMPLE SIZE, not the honesty flag.
    cand_no_plan = bs._us_candidate_no_plan_sample(full_buy, set(), sample_size=3)
    assert cand_no_plan["all_no_plan"] is True
    html = _render_stocks({
        "us_standouts": {"buy": full_buy, "ran": [], "eligible": len(full_buy)},
        "gate": _DUMMY_GATE,
        "us_prophet_book": _prophet_book(plans=[]),
        "cand_no_plan": cand_no_plan,
    })
    assert html.count('class="cand-row"') == 3, (
        f"expected exactly 3 baked .cand-row elements (gate.preview), found "
        f"{html.count('class=\"cand-row\"')}")


def test_b4_template_footer_is_conditional_on_the_flag():
    honest_html = _render_stocks({
        "us_standouts": {"buy": [_board_row(ticker="X", name="X Corp")], "ran": [], "eligible": 1},
        "gate": None,
        "us_prophet_book": _prophet_book(plans=[]),
        "cand_no_plan": {"sample": [{"ticker": "X", "name": "X Corp", "price": 1.0}],
                          "all_no_plan": True},
    })
    assert "that carry no plan yet" in honest_html
    assert "some already carry a plan" not in honest_html

    dishonest_html = _render_stocks({
        "us_standouts": {"buy": [_board_row(ticker="X", name="X Corp")], "ran": [], "eligible": 1},
        "gate": None,
        "us_prophet_book": _prophet_book(plans=[]),
        "cand_no_plan": {"sample": [{"ticker": "X", "name": "X Corp", "price": 1.0}],
                          "all_no_plan": False},
    })
    assert "some already carry a plan" in dishonest_html
    assert "that carry no plan yet" not in dishonest_html


# ─────────────────────────── S1 — plan-book gate fails CLOSED ─────────────

def test_s1_life_gate_cfg_closes_on_config_exception():
    real_config = bs.config

    class _Boom:
        @staticmethod
        def load():
            raise RuntimeError("config unreadable")

    try:
        bs.config = _Boom()
        assert bs._us_life_gate_cfg() is True, (
            "a config-load exception must default the PLAN-BOOK gate to True "
            "(fail closed) — the candidate board's own _us_board_gate_cfg() stays "
            "fail-open by design; this reader exists specifically to differ")
    finally:
        bs.config = real_config


def test_s1_life_gate_cfg_closes_when_gated_key_absent():
    real_config = bs.config

    class _NoGatedKey:
        @staticmethod
        def load():
            return {"us_board_gate": {"preview_rows": 3}}  # no "gated" key at all

    try:
        bs.config = _NoGatedKey()
        assert bs._us_life_gate_cfg() is True
    finally:
        bs.config = real_config


def test_s1_life_gate_cfg_still_honors_an_explicit_false():
    real_config = bs.config

    class _ExplicitOff:
        @staticmethod
        def load():
            return {"us_board_gate": {"gated": False}}

    try:
        bs.config = _ExplicitOff()
        assert bs._us_life_gate_cfg() is False, (
            "fail-closed is a DEFAULT, not a forced override — an operator's "
            "explicit gated:false must still be honored")
    finally:
        bs.config = real_config


# ─────────────────────────── S2 — candidate join off the full board ───────

def test_s2_plan_card_join_uses_the_full_candidate_map_when_threaded():
    # OFF is a candidate row NOT present in the (sliced) us_standouts.buy the
    # template would otherwise build its join map from — only reachable via
    # the server-computed us_candidate_map (finding S2).
    plan = _prophet_plan(asset="OFF")
    html = _render_stocks({
        "us_standouts": {"buy": [_board_row(ticker="ONLY-IN-PREVIEW")], "ran": [], "eligible": 1},
        "us_prophet_book": _prophet_book(plans=[plan]),
        "us_candidate_map": {"OFF": {"ticker": "OFF", "name": "Off Board Inc",
                                      "sector": "Energy", "price": 12.34}},
    })
    assert "Off Board Inc" in html, (
        "the plan card's ticker (OFF) is not in the sliced us_standouts.buy, so "
        "only the FULL server-side map (us_candidate_map) can supply its name")


# ─────────────────────────── S3 — hydrate staleness ────────────────────────
# (the round-1 dense-cap half of S3 is REMOVED — see R1/R3 below)

def test_s3_hydrate_no_longer_blind_appends_into_the_initialized_grid():
    html = _render_stocks({"us_prophet_book": _prophet_book(), "gate": _DUMMY_GATE})
    assert "insertAdjacentHTML('beforeend', payload.plan_cards_html)" not in html, (
        "appending straight into #us-life-grid leaves its show-more bar "
        "permanently stale (initShowMore is idempotent per element)")
    assert "freshLifeGrid" in html, (
        "the hydrate fix must build a FRESH grid element, same documented "
        "pattern as _pvcPaint's own W-L1 comment")


# ─────────────────── R1+R3 — dense cap REMOVED (round-2 finding) ──────────
# COMMISSIONING ADJUDICATION: a hard 40-card cap that physically removed
# cards past the cap broke the ladder filter for every cell whose members
# sort mostly past position 40 — on the real committed book, Delivering(1)/
# Invalidated(4)/Resolved(26) went DEAD for a hydrated (signed-in) viewer,
# and S9's new zero-state then printed "No plans match this filter" under a
# ladder cell reading a nonzero count. MP-1 §10's dense clause is DEFERRED
# WHOLESALE to a follow-up wave that builds a real plan-book table view.

def test_r1_r3_dense_cap_machinery_fully_removed():
    html = _render_stocks({"us_prophet_book": _prophet_book(), "gate": _DUMMY_GATE})
    assert "__usLifeDenseCap" not in html
    assert 'id="us-life-dense-more"' not in html
    assert "mx-dense-more" not in html
    # The fresh-grid swap legitimately removeChild()s the OLD container node
    # and its stale sm-bar sibling (that part is kept — it fixed a real,
    # separate defect). What must be gone is per-CARD removal past a cap.
    assert "removeChild(cards[i])" not in html, (
        "hydrate() must not remove any individual card it just merged in")
    assert "CAP = 40" not in html and "cards.length > CAP" not in html


def test_r1_r3_hydrate_preserves_every_plan_row_against_the_real_payload():
    """Regression for the R1/R3 finding, against the REAL committed book
    (site/prophet/index.json) rather than a synthetic fixture — the bug was
    specifically about where Delivering/Invalidated/Resolved rows actually
    SORT on a real night (first resolved row at index 63), which a small
    synthetic fixture would not reproduce. After the fresh-grid hydrate merge
    (shell preview HTML + hydrated locked-rows HTML, nothing removed), every
    plan row must be present, and every ladder cell with a nonzero published
    count must have at least one matching `data-life` card somewhere in the
    combined DOM."""
    payload_path = ROOT / "site" / "prophet" / "index.json"
    if not payload_path.exists():
        pytest.skip("site/prophet/index.json not present in this checkout")
    book = json.loads(payload_path.read_text())
    plans = book.get("plans") or []
    counts = book.get("lifecycle_counts") or {}
    if not plans or not any(counts.values()):
        pytest.skip("real payload has no plans / no nonzero lifecycle cells to test against")

    shell_book, life_gate, locked_plans = bs._split_us_prophet_board(book, 3, gated=True)
    assert life_gate is not None and locked_plans, "fixture assumption: the real book is gated"
    episodes = bs._us_prophet_episode_map(plans)

    shell_html = _env().get_template("_us_prophet_plan_cards.html.j2").render(
        items=shell_book["plans"], cand_map={}, trg_map={}, episode_map=episodes)
    payload_html = _env().get_template("_us_prophet_plan_cards.html.j2").render(
        items=locked_plans, cand_map={}, trg_map={}, episode_map=episodes)
    combined = shell_html + payload_html

    # Every plan row is present — the fresh-grid merge is a pure concatenation.
    assert combined.count("data-life=") == len(plans)

    # Every nonzero cell (Delivering/Invalidated/Resolved included) is reachable.
    dead_cells = [k for k, n in counts.items() if n and f'data-life="{k}"' not in combined]
    assert not dead_cells, (
        f"ladder cell(s) {dead_cells} are nonzero in lifecycle_counts but have "
        f"NO matching card in the hydrated DOM — this is exactly the R1/R3 "
        f"regression (a cap or other filter silently dropped rows)")


# ─────────────────────────── S4 — empty state cause line ──────────────────

def test_s4_empty_state_carries_mx_empty_why():
    html = _render_stocks({"us_prophet_book": _prophet_book(plans=[])})
    assert 'class="mx-empty"' in html
    assert 'class="mx-empty-why"' in html


# ─────────────────────────── S5 — ratified watch-absence ZH string ────────

def test_s5_watch_absence_zh_string_is_the_ratified_one():
    book = _prophet_book()
    book["intake"] = {}  # early_turn_watch key entirely absent
    html = _render_stocks({"us_prophet_book": book})
    assert "观察档自下一次夜间构建起发布。" in html
    assert "「观察」将在下一次收盘更新后发布。" not in html


# ─────────────────────────── S6 — episode chip ruling ─────────────────────

def test_s6_episode_chip_matches_the_ruling_verbatim():
    plans = [
        _prophet_plan(id="ACME-1", asset="ACME", entry_date="2026-08-05", closed=False),
        _prophet_plan(id="ACME-0", asset="ACME", entry_date="2026-07-01",
                       lifecycle_state="resolved", closed=True),
    ]
    html = _render_stocks({
        "us_prophet_book": _prophet_book(plans=plans),
        "us_prophet_episodes": bs._us_prophet_episode_map(plans),
    })
    assert "Episode 2 · opened Aug 5" in html, html
    assert "第 2 轮 · 8月5日启动" in html
    assert "Episode 2 of 2" not in html
    assert "共 2 轮" not in html
    assert "2026-08-05" not in html  # the raw ISO string must never leak into the chip


# ─────────────────────────── S7 — wall copy counts rows, not names ────────

def test_s7_wall_copy_says_plan_rows_not_names():
    plans = [_prophet_plan(id=f"P{i}", asset=f"T{i}") for i in range(5)]
    book = _prophet_book(plans=plans)
    shell_book, life_gate, _locked = bs._split_us_prophet_board(book, 3, gated=True)
    html = _render_stocks({"us_prophet_book": shell_book, "life_gate": life_gate})
    assert "plan rows on tonight's board" in html
    assert "more names on tonight's board" not in html
    assert "plan rows. Sign in" in html
    assert "names. Sign in" not in html


# ─────────────────────────── S8 — resolved row inflates the preview claim ─

def test_s8_visible_preview_count_excludes_resolved_rows():
    shell_book = {"plans": [
        {"lifecycle_state": "resolved"},
        {"lifecycle_state": "entered"},
        {"lifecycle_state": "ready"},
    ]}
    assert bs._us_life_visible_preview_count(shell_book) == 2


def test_s8_wall_quotes_the_visible_count_when_a_resolved_row_sorts_top():
    plans = [
        _prophet_plan(id="R1", asset="R1", lifecycle_state="resolved", closed=True),
        _prophet_plan(id="A1", asset="A1", lifecycle_state="entered"),
        _prophet_plan(id="A2", asset="A2", lifecycle_state="ready"),
        _prophet_plan(id="A3", asset="A3", lifecycle_state="ready"),
        _prophet_plan(id="A4", asset="A4", lifecycle_state="ready"),
    ]
    book = _prophet_book(plans=plans)
    shell_book, life_gate, _locked = bs._split_us_prophet_board(book, 3, gated=True)
    assert life_gate["preview"] == 3  # the raw slice — includes the resolved row
    visible = bs._us_life_visible_preview_count(shell_book)
    assert visible == 2
    html = _render_stocks({"us_prophet_book": shell_book, "life_gate": life_gate,
                            "life_gate_visible_preview": visible})
    assert "first 2 of" in html
    assert "first 3 of" not in html


def test_r4_wall_arithmetic_stays_honest_when_a_resolved_row_sorts_top():
    """Repair round 2, finding R4: once the wall's "first N" figure is the
    honest visible count (S8), its "N more" figure must be that count's
    arithmetic complement — round-1 shipped "first 2 of 262" beside "259
    more" (2+259=261, not 262). visible_preview + visible_locked must equal
    the quoted total."""
    plans = ([_prophet_plan(id="R1", asset="R1", lifecycle_state="resolved", closed=True)]
             + [_prophet_plan(id=f"A{i}", asset=f"A{i}", lifecycle_state="ready")
                for i in range(4)])
    book = _prophet_book(plans=plans)
    shell_book, life_gate, _locked = bs._split_us_prophet_board(book, 3, gated=True)
    ctx = bs._us_life_repair_context({"us_standouts": None, "us_prophet_book": book},
                                      shell_book, life_gate, 3)
    visible_preview = ctx["life_gate_visible_preview"]
    visible_locked = ctx["life_gate_visible_locked"]
    assert visible_preview == 2
    assert visible_locked == life_gate["total"] - visible_preview
    assert visible_preview + visible_locked == life_gate["total"] == len(plans)

    html = _render_stocks({"us_prophet_book": shell_book, "life_gate": life_gate,
                            **ctx})
    assert f"first {visible_preview} of {life_gate['total']}" in html
    assert f"{visible_locked} more plan rows" in html
    # The two quoted numbers must literally sum to the quoted total.
    assert visible_preview + visible_locked == 5


# ─────────────────────────── S9 — silent zero-match filter ────────────────

def test_s9_zero_state_element_and_setlife_wiring_present():
    html = _render_stocks({"us_prophet_book": _prophet_book()})
    assert 'id="us-life-filter-zero"' in html
    assert "us-life-filter-zero" in html.split("function setLife")[1].split("function boot")[0] \
        if "function setLife" in html else False


# ─────────────────────────── N3 — stale #us-tier-wall id ──────────────────

def test_n3_hydrate_teardown_targets_the_real_wall_id():
    # P0 #6185 (D3, FROZEN SPEC): 'us-tier-wall' is no longer a stale
    # pre-migration id — B4 restored it as the CANDIDATE wall's own real id
    # (distinct from the plan wall's 'us-life-wall'), so hydrate() teardown
    # must now remove BOTH walls by their own ids, never just one.
    html = _render_stocks({"us_prophet_book": _prophet_book(), "gate": _DUMMY_GATE})
    assert "getElementById('us-tier-wall')" in html
    assert "getElementById('us-life-wall')" in html
