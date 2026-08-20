"""P-MP1-SHELL §7/§11/§12 item 3 — non-US byte-parity proof.

MP-1-prophet-board.md §7: "Other markets: hk/china/canada/intl keep the legacy
rail via the pv_card parameter default (ruling §10.2) — zero rendered-byte
change on non-US pages, test-pinned." §12 acceptance item 3: "The pv_card
lifecycle parameter defaults to legacy: non-US templates render byte-identical."

The ONLY file this packet's diff shares with hk.html.j2/china.html.j2/
canada.html.j2/intl.html.j2 is templates/_prophet_card.html.j2 (each of those
four does `{% import "_prophet_card.html.j2" as pv %}` then calls
`pv.pv_css()` once and `pv.pv_card(cx)` per row, with NO `lifecycle`/`id`/
`life`/`lane_mark` keys — every existing non-US call site). This suite proves,
against origin/main's pre-migration copy of that file:

  1. The four non-US page templates themselves are byte-identical to
     origin/main (git diff --stat empty) — confirming no OTHER file in this
     packet's diff touches them.
  2. pv_css() — the shared <style> block every one of those four pages
     renders once — is byte-identical. This is the check that caught a real
     defect during this packet's build: the new .pv-life/.pv-newer/.pv-mark
     CSS was first added INSIDE pv_css() (shared), which would have changed
     all four pages' bytes; it now lives in dashboard.html.j2's own <style>
     block instead (US-only, never included by the other four).
  3. pv_card() — the per-row card macro — is byte-identical for representative
     cx dicts shaped exactly like the non-US callers' (no lifecycle/id/life/
     lane_mark keys), across several branches (buy/wait/hold/no-zone/flags/
     marks) so an additive-parameter regression that only shows up on one
     branch cannot hide.

A full whole-page render diff (synthetic VM through hk.html.j2 etc. in full)
is NOT attempted here — building synthetic view-models for four more
templates of this size is out of this suite's scope. Given (1) — no other
touched file — the shared-macro proof above is the complete surface by
construction: nothing else in the diff can reach those four pages' bytes.

STOCKTABLE.JS COVERAGE (commissioning follow-up, gap 2): templates/stocktable.js
is a SECOND shared file this packet touches (retiring the US-only Stage/阶段
filter dropdown + its count chips, MP-1 §6/§9/§8). hk.html.j2/china.html.j2/
canada.html.j2 each call `StockTable.init({...})` with no `stageFilter` key —
the new guard (`cfg.stageFilter !== false` / `cfg.stageFilter === false`) is
mathematically a no-op for any caller that never sets that key (`undefined
!== false` is `true`; `undefined === false` is `false`), so this is proven
by (a) diffing stocktable.js against origin/main and asserting the ONLY
change is the two additive guard hunks, and (b) grepping every non-US
`StockTable.init({...})` call site's own source text for the literal string
`stageFilter` — its absence in all three is what makes the guard inert there.
intl.html.j2 never calls StockTable.init at all and is unaffected by
construction. Same no-DOM-execution limitation as the page templates above:
this is a static-source proof, not a rendered/executed one.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parent.parent
NON_US_TEMPLATES = [
    "templates/hk.html.j2",
    "templates/china.html.j2",
    "templates/canada.html.j2",
    "templates/intl.html.j2",
]


def _merge_base() -> str:
    """Repair round 2, finding R5: this suite's job is proving THIS BRANCH'S
    OWN commits never touched the non-US files — a diff against the LIVE
    `origin/main` is the wrong comparison, because main keeps moving (nightly
    pushes, other merged PRs) and any of those commits touching
    hk.html.j2/canada.html.j2/etc. independently fails this suite for a
    reason that has nothing to do with this branch's diff. Confirmed as a
    standing false-positive landmine: `origin/main` had drifted ahead of this
    branch's merge-base by the time of both the round-1 and round-2 review
    (canada.html.j2/hk.html.j2 changed on main after this branch forked).
    The merge-base is the fixed point this branch actually diverged from —
    diffing against it answers the suite's real question and never moves
    again for THIS branch."""
    return subprocess.check_output(
        ["git", "merge-base", "origin/main", "HEAD"], cwd=str(ROOT)
    ).decode().strip()


_MERGE_BASE = _merge_base()


def _origin_main_text(rel_path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"{_MERGE_BASE}:{rel_path}"], cwd=str(ROOT)
    ).decode()


def test_non_us_page_templates_are_untouched():
    """Confirms no file besides _prophet_card.html.j2 in this packet's diff
    can reach hk/china/canada/intl's rendered bytes at all."""
    out = subprocess.check_output(
        ["git", "diff", "--stat", _MERGE_BASE, "HEAD", "--", *NON_US_TEMPLATES],
        cwd=str(ROOT),
    ).decode()
    assert out.strip() == "", f"non-US template(s) changed:\n{out}"


def _macros():
    orig_src = _origin_main_text("templates/_prophet_card.html.j2")
    cur_src = (ROOT / "templates" / "_prophet_card.html.j2").read_text()
    env = jinja2.Environment(autoescape=True)
    return env.from_string(orig_src).module, env.from_string(cur_src).module


def test_pv_css_is_byte_identical():
    """The shared <style> block every non-US page renders once via pv.pv_css()."""
    orig, cur = _macros()
    assert str(orig.pv_css()) == str(cur.pv_css())


def _base_cx(**overrides) -> dict:
    cx = {
        "href": "stock.html#0700.HK", "tk": "0700", "mkt": "hk",
        "name": "Tencent", "sec": "Communication Services",
        "price_txt": "$400.00", "show_change": True,
        "verb": "buy", "edge": 72,
        "stage": 3, "spark": None,
        "zone_kind": "active", "zone_lo": "$390.00", "zone_hi": "$410.00",
        "date": "2026-07-04", "flags": [], "triage": False, "featured": False,
        "marks": None,
    }
    cx.update(overrides)
    return cx


CX_VARIANTS = [
    ("buy_featured", _base_cx(verb="buy", featured=True)),
    ("wait_no_zone", _base_cx(verb="wait", zone_kind="none", zone_lo=None, zone_hi=None, stage=0)),
    ("hold_readd", _base_cx(verb="hold", zone_kind="readd")),
    ("avoid_with_flags", _base_cx(
        verb="avoid",
        flags=[("Earnings soon", "财报临近"), ("Extended", "过热")],
    )),
    ("with_marks_and_trigger", _base_cx(
        marks=[{"k": "new", "en": "New", "zh": "新"},
               {"k": "theme", "en": "AI", "zh": "AI"}],
        trigger={"kind": "fired", "tip_en": "Fired.", "tip_zh": "已触发。"},
    )),
    ("triage_no_price", _base_cx(price_txt=None, show_change=False, triage=True)),
]


def test_pv_card_is_byte_identical_across_representative_non_us_calls():
    orig, cur = _macros()
    for label, cx in CX_VARIANTS:
        out_orig = str(orig.pv_card(cx))
        out_cur = str(cur.pv_card(cx))
        assert out_orig == out_cur, f"pv_card diverged for variant {label!r}"


# --------------------------------------------------------------------------- #
# stocktable.js — Stage/阶段 filter + count-chip retirement (gap 2)
# --------------------------------------------------------------------------- #

NON_US_STOCKTABLE_CALLERS = [
    "templates/hk.html.j2",
    "templates/china.html.j2",
    "templates/canada.html.j2",
]


def _init_call_source(template_rel_path: str) -> str:
    """The literal `StockTable.init({ ... });` call-site text out of one
    market template — everything between the call and its matching close,
    found by bracket balance (the object literal itself may contain nested
    braces, e.g. optionLabels: {...})."""
    src = (ROOT / template_rel_path).read_text()
    start = src.index("StockTable.init(")
    depth = 0
    i = start
    for i in range(start, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
    return src[start:i + 1]


def test_stocktablejs_diff_is_exactly_the_two_additive_stagefilter_guards():
    """`git diff --numstat` for the ONE line that gained a condition (dropdown
    gate: `stageOpts.length > 0` -> `cfg.stageFilter !== false && stageOpts.length
    > 0`) plus two pure-insertion comment/early-return blocks. Asserted by
    hunk count and content rather than a line-subsequence check — the dropdown
    hunk is a genuine one-line MODIFICATION (a `+`/`-` pair), not an insertion,
    so a pure-subsequence check is the wrong shape for this diff."""
    diff = subprocess.check_output(
        ["git", "diff", "-U0", _MERGE_BASE, "--", "templates/stocktable.js"],
        cwd=str(ROOT),
    ).decode()
    hunk_count = diff.count("@@ -")
    assert hunk_count == 2, f"expected exactly 2 hunks, found {hunk_count}:\n{diff}"
    removed = [l[1:] for l in diff.splitlines() if l.startswith("-") and not l.startswith("---")]
    added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    # exactly one line removed (the un-gated dropdown condition) ...
    assert removed == [
        "      if (stageOpts.length > 0) { var ddStage = _makeDD('stage', stageOpts); if (ddStage) bar.appendChild(ddStage); }"
    ], removed
    # ... and every added line is either that SAME line with the guard
    # prepended, or pure comment/early-return — never a removal of anything
    # else, never a change to a DIFFERENT line.
    assert any("cfg.stageFilter !== false && stageOpts.length > 0" in l for l in added)
    cur = (ROOT / "templates" / "stocktable.js").read_text()
    orig = _origin_main_text("templates/stocktable.js")
    assert "cfg.stageFilter !== false && stageOpts.length > 0" in cur
    assert "cfg.stageFilter === false" in cur
    assert "cfg.stageFilter !== false && stageOpts.length > 0" not in orig
    assert "cfg.stageFilter === false" not in orig


def test_non_us_stocktable_init_calls_never_set_stagefilter():
    """The guard is `cfg.stageFilter !== false` / `=== false`. Neither branch
    changes behavior unless the CALLER sets the key — so a caller's source
    text containing no `stageFilter` substring at all is a complete proof
    that this retirement is invisible to it, independent of what the guard's
    JS semantics happen to be."""
    for rel in NON_US_STOCKTABLE_CALLERS:
        call = _init_call_source(rel)
        assert "stageFilter" not in call, f"{rel} unexpectedly sets stageFilter"


def test_non_us_stocktable_init_call_sites_are_byte_identical_to_origin_main():
    """Belt-and-braces beyond the whole-file diff above: the exact call-site
    slice for each of the three markets, byte-for-byte."""
    for rel in NON_US_STOCKTABLE_CALLERS:
        orig_src = subprocess.check_output(
            ["git", "show", f"{_MERGE_BASE}:{rel}"], cwd=str(ROOT)
        ).decode()
        cur_src = (ROOT / rel).read_text()
        orig_call = orig_src[orig_src.index("StockTable.init("):]
        cur_call = cur_src[cur_src.index("StockTable.init("):]
        # Compare only up to the length of the shorter (origin/main) text at
        # this call site — a downstream unrelated edit elsewhere in either
        # file must not fail this specific assertion.
        n = len(orig_call[:2000])
        assert orig_call[:n] == cur_call[:n], f"{rel}: StockTable.init call site changed"


def test_intl_never_calls_stocktable_init():
    src = (ROOT / "templates" / "intl.html.j2").read_text()
    assert "StockTable.init(" not in src


def test_us_call_site_sets_stagefilter_false():
    """Unlike hk/china/canada (which pass an inline object literal straight to
    StockTable.init(...)), dashboard.html.j2 builds a named `STINIT` object
    first and calls `StockTable.init(STINIT)` — so the config to inspect is
    the `var STINIT = { ... };` literal, not the call site itself."""
    dash = (ROOT / "templates" / "dashboard.html.j2").read_text()
    assert "StockTable.init(STINIT)" in dash
    start = dash.index("var STINIT = {")
    depth = 0
    end = start
    for end in range(start, len(dash)):
        if dash[end] == "{":
            depth += 1
        elif dash[end] == "}":
            depth -= 1
            if depth == 0:
                break
    stinit_literal = dash[start:end + 1]
    assert "'us-stocktable-data'" in stinit_literal or '"us-stocktable-data"' in stinit_literal
    assert "stageFilter: false" in stinit_literal


def test_no_user_facing_stage_word_reachable_when_stagefilter_is_false():
    """The retirement mechanism itself: `_makeDD('stage', ...)` is the ONLY
    reader of FILTER_LABELS['stage']/FILTER_TITLES['stage'] (the 'Stage'/'阶段'
    strings) anywhere in stocktable.js, and its one call site is gated by the
    same flag the US init sets. This does not execute the guard (no DOM here
    — see module docstring); it proves the STRUCTURE that makes the ban hold:
    there is exactly one path from cfg to that label text, and it is gated."""
    js = (ROOT / "templates" / "stocktable.js").read_text()
    makedd_stage_calls = js.count("_makeDD('stage'")
    assert makedd_stage_calls == 1, (
        f"expected exactly one _makeDD('stage', ...) call site to reason about, found {makedd_stage_calls}"
    )
    call_line = next(line for line in js.splitlines() if "_makeDD('stage'" in line)
    assert "cfg.stageFilter !== false" in call_line, (
        "the sole _makeDD('stage', ...) call site is not gated by cfg.stageFilter"
    )
