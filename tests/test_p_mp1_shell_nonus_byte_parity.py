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

  1. B1 MERGE-SAFETY FIX (2026-09-01 repair round 1, independent code review):
     items 1 and 2 below USED TO diff each file against `git merge-base
     origin/main HEAD` and assert a specific NON-EMPTY diff shape (an itemized
     added-date-rollout pin, or a 2-line pv_css() pin). That mechanism
     self-destructs the moment this PR merges: once `origin/main` contains
     this branch's commits, the merge-base of a later checkout IS (or
     descends past) this branch's own HEAD, so `_origin_main_text()` reads
     back the SAME post-rollout content `cur` already holds — the computed
     diff collapses to empty, and an assertion that expects a non-empty,
     itemized diff goes red forever. Fixed by dropping merge-base diffing
     entirely for the two tests that assert a SPECIFIC diff shape: they now
     pin exact SHA-256 hashes of the CURRENT (post-rollout) raw file bytes —
     no diffing, no historical baseline, no leniency of any kind (not
     comment-stripped, not sorted-line-set matched — literal bytes). A
     future legitimate edit to any of these five surfaces must recompute and
     update its pin by hand; that friction IS the guard's job — unrelated
     drift (or a bug that silently changes shared markup) breaks the pin
     without needing to know or care where `origin/main` currently sits.

     R6 CORRECTION (2026-09-01 repair round 3, independent repair-delta
     review): round 1's docstring claimed "`_merge_base()`/`_origin_main_
     text()` remain in use below ONLY by the pv_card()-output-equality test
     and the stocktable.js diff test, which both assert 'no diff at all' /
     a PRE-EXISTING (unrelated) shape rather than a rollout-specific
     non-empty diff — see their own docstrings for why those two are
     unaffected by this failure mode." That claim was FALSE for the
     stocktable.js diff test specifically, and round 1 never verified it:
     `test_stocktablejs_diff_is_exactly_the_two_additive_stagefilter_guards`
     asserted `hunk_count == 2` against `git diff -U0 $MERGE_BASE --
     templates/stocktable.js` — a SPECIFIC non-empty diff shape, the exact
     pattern item 1 warns about, not a "no diff at all" equality check. It
     was red on this exact head in CI pack 9: templates/stocktable.js's git
     blob (f8145bd6fb4ed0adba5f34b5c97a7895b7332f2e) is IDENTICAL at
     origin/main, at this branch's own merge-base, AND at HEAD — this
     branch's own commits never touched the file at all, so the two
     additive `stageFilter` guards the test exists to protect had already
     landed on main (from an earlier, unrelated change) before this
     branch's merge-base — collapsing the diff to 0 hunks regardless of
     when the test runs, not merely after this PR merges. Fixed the same
     way as item 1: `test_stocktablejs_is_byte_pinned_and_carries_both_
     stagefilter_guards` below drops the diff assertion and pins the
     CURRENT file's exact SHA-256 bytes (losing nothing — those bytes
     already ARE the fully-guarded post-rollout file) plus a direct
     substring check for both guards, no git dependency at all.

     Precise accounting of what remains true, so this docstring makes no
     further false assurances: `_merge_base()`/`_origin_main_text()` are
     still used by exactly two tests below —
     `test_pv_card_is_byte_identical_across_representative_non_us_calls`
     (via `_macros()`) and
     `test_non_us_stocktable_init_call_sites_are_byte_identical_to_origin_main`.
     Both assert EQUALITY ("no diff at all" between the origin/main-sourced
     text and the current text) rather than a specific non-empty diff
     shape — the collapse this section describes makes `orig`/`cur` (or
     `orig_call`/`cur_call`) identical BY CONSTRUCTION once merge-base
     reaches this branch's own HEAD, which keeps an equality assertion
     trivially true (never red), unlike a shape assertion that expects a
     particular non-empty diff and has nothing left to match once the diff
     empties out. Both genuinely survive; neither was re-verified to be
     false the way the stocktable.js diff test was, and both remain
     git-dependent (a legitimate future non-US template/stocktable.js edit
     on either side of the merge-base could still change what they compare,
     just never turn a currently-passing run red from the collapse itself).
  2. pv_css() — the shared <style> block every one of those four pages
     renders once — is byte-pinned (SHA-256 of the exact rendered CSS text).
     This is the check that caught a real defect during this packet's build:
     the new .pv-life/.pv-newer/.pv-mark CSS was first added INSIDE pv_css()
     (shared), which would have changed all four pages' bytes; it now lives
     in dashboard.html.j2's own <style> block instead (US-only, never
     included by the other four). The Added-date rollout's
     `.pv-added`/`.pv-dt+.pv-added` rules DO belong in this shared block
     (they render on every market, not US-only), and F1 (2026-09-01 repair
     round) further changed `.pv-znr`/`.pv-dt`/`.pv-added`'s flex-shrink
     behavior so the buy-zone price chip never loses the space fight to the
     Added-date metadata chip — `test_pv_css_is_byte_pinned_post_rollout`
     pins the CURRENT full CSS text exactly, superseding the old two-line
     diff pin (which could not express "these three rules changed together"
     without becoming exactly this — a whole-content hash).
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
is a SECOND shared file in scope (retiring the US-only Stage/阶段 filter
dropdown + its count chips, MP-1 §6/§9/§8) — its two additive `stageFilter`
guards are already present at `origin/main`, at this branch's merge-base, and
at HEAD alike (R6, see item 1 above), so it is more precisely "a file this
program's design touches" than "a file this branch's diff touches" today.
hk.html.j2/china.html.j2/canada.html.j2 each call `StockTable.init({...})`
with no `stageFilter` key — the guard (`cfg.stageFilter !== false` /
`cfg.stageFilter === false`) is mathematically a no-op for any caller that
never sets that key (`undefined !== false` is `true`; `undefined === false`
is `false`), so this is proven by (a) pinning stocktable.js's current bytes
exactly and asserting both guard substrings are present in them (R6 —
replaces the old origin/main diff, which could not survive the merge-base
collapse for a file this branch never itself modifies), and (b) grepping
every non-US `StockTable.init({...})` call site's own source text for the
literal string `stageFilter` — its absence in all three is what makes the
guard inert there. intl.html.j2 never calls StockTable.init at all and is
unaffected by construction. Same no-DOM-execution limitation as the page
templates above: this is a static-source proof, not a rendered/executed one.
"""
from __future__ import annotations

import hashlib
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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: B1 (2026-09-01 repair round): exact SHA-256 of each non-US template's
#: CURRENT raw file bytes — see the module docstring's item 1 for why this
#: replaced the merge-base functional-diff mechanism. No comment-stripping,
#: no leniency: literal file bytes. A legitimate future edit to any of these
#: four templates must recompute and update its hash here.
_EXPECTED_TEMPLATE_SHA256: dict[str, str] = {
    "templates/hk.html.j2": "6e45058c198822f2580e3874ac48899f6a1cb45bf89df16548c374cdedef64a6",
    "templates/china.html.j2": "cb6e0685b96a6d897e9562418927c0bb5d5e656d4b31c99e843ec5f213fa7031",
    "templates/canada.html.j2": "a108840bc92567faaa7fabaf9c6778c1ef33a63da59111fc847dabc86f2e36bc",
    "templates/intl.html.j2": "c62b4a6373ac3130a16f622b8dae9b73218642e261051a3bd3493fc95fd0d9a5",
}


def test_non_us_templates_are_byte_pinned_post_rollout():
    """Merge-safe successor to the old merge-base functional-diff test (B1):
    pins each non-US template's CURRENT raw bytes exactly, with no comparison
    to any historical baseline — so this assertion's truth value does not
    depend on whether/when this branch has merged. Simulated merge-base==HEAD
    (the exact failure mode B1 fixes) changes NOTHING here: this test never
    calls git at all."""
    for rel_path in NON_US_TEMPLATES:
        cur = (ROOT / rel_path).read_text(encoding="utf-8")
        assert _sha256_text(cur) == _EXPECTED_TEMPLATE_SHA256[rel_path], (
            f"{rel_path}: content drifted from its pinned post-rollout hash — "
            f"if this is a legitimate edit, recompute and update the pin")


def _macros():
    orig_src = _origin_main_text("templates/_prophet_card.html.j2")
    cur_src = (ROOT / "templates" / "_prophet_card.html.j2").read_text()
    env = jinja2.Environment(autoescape=True)
    return env.from_string(orig_src).module, env.from_string(cur_src).module


#: B1 (2026-09-01 repair round 1): exact SHA-256 of the CURRENT pv_css() render
#: output — supersedes the old two-line merge-base diff pin (same failure
#: mode as the template pin above: a merge-base==HEAD comparison collapses to
#: an empty diff and an assertion expecting a non-empty one goes red). Covers
#: both the Added-date rollout's `.pv-added`/`.pv-dt+.pv-added` rules AND F1's
#: (2026-09-01 repair round 1) `.pv-znr`/`.pv-dt`/`.pv-added` flex-shrink fix
#: (the buy-zone price chip must never lose the space fight to the Added-date
#: metadata chip). Recomputed for round 3's R4 (.pv-znr gains its own bounded
#: max-width:100%;overflow:hidden;text-overflow:ellipsis so a pathologically
#: long zone string ellipsizes instead of hard-clipping) and R5 (the ≤680px
#: max-width:32% cap is scoped to `.pv-added` only, not `.pv-dt`).
#:
#: RECOMPUTED 2026-09-02 for the zone-shelf FOLD (Chairman visibility report):
#: `.pv-zn` gains `flex-wrap:wrap` + a 2px row-gap, `.pv-added` becomes
#: `flex:0 0 auto` with no overflow/ellipsis and no padding-left (it folds to
#: its own line instead of truncating), `.pv-znm` is hardened to `.pv-znr`'s
#: flex:none + bounded-ellipsis contract, and the ≤680px `max-width:32%`
#: truncation cap is removed. CSS-only: `pv_card()`'s markup is byte-unchanged,
#: which `test_pv_card_is_byte_identical_across_representative_non_us_calls`
#: below proves independently. The pin MECHANISM is untouched — this is a
#: recomputed value, not a weakened assertion. A legitimate future edit to
#: pv_css() must recompute and update this hash again.
_EXPECTED_PV_CSS_SHA256 = "e7dd2cf07a44230d9a1b9a82b335943070ca0bad76e6fc7c1b99aa0625a12258"


def test_pv_css_is_byte_pinned_post_rollout():
    """The shared <style> block every non-US page renders once via pv.pv_css().
    No git dependency — reads only the current file on disk, so this is
    immune to the merge-base==HEAD collapse B1 fixes (see module docstring)."""
    cur_src = (ROOT / "templates" / "_prophet_card.html.j2").read_text()
    cur = jinja2.Environment(autoescape=True).from_string(cur_src).module
    css = str(cur.pv_css())
    assert _sha256_text(css) == _EXPECTED_PV_CSS_SHA256, (
        "pv_css() drifted from its pinned post-rollout hash — if this is a "
        "legitimate edit, recompute and update the pin")


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


#: R6 (2026-09-01 repair round 3): exact SHA-256 of the CURRENT
#: templates/stocktable.js raw bytes. Same merge-safety reasoning as the B1
#: template pins above (module docstring item 1) applies here, confirmed
#: independently in round 3: templates/stocktable.js's git blob
#: (f8145bd6fb4ed0adba5f34b5c97a7895b7332f2e) is IDENTICAL at origin/main,
#: at this branch's own merge-base, AND at HEAD — this branch never itself
#: modified the file, so the predecessor test's `git diff -U0 $MERGE_BASE`
#: was always going to collapse to 0 hunks, not merely after a future
#: merge. Pinning current bytes loses nothing: those bytes already ARE the
#: fully-guarded post-rollout file. A legitimate future edit to
#: templates/stocktable.js must recompute and update this hash.
_EXPECTED_STOCKTABLEJS_SHA256 = "56f6f93366f2e21024b4cd5c971766a7c9506aea49c21b37b428674b8f086819"


def test_stocktablejs_is_byte_pinned_and_carries_both_stagefilter_guards():
    """Merge-safe successor to
    test_stocktablejs_diff_is_exactly_the_two_additive_stagefilter_guards
    (R6, round 3): that test asserted a SPECIFIC non-empty diff shape
    (`hunk_count == 2`) against `git diff -U0 $MERGE_BASE --
    templates/stocktable.js` — measured RED on this exact head, in this
    exact file, inside CI pack 9, because the file's bytes are already
    identical at origin/main, this branch's merge-base, and HEAD (see the
    hash comment above). This test drops the diff entirely: it pins the
    CURRENT file's raw bytes exactly (no git dependency, immune to any
    future merge-base movement) and asserts the two additive `stageFilter`
    guards the retired test existed to protect are directly present in the
    file text — the property that mattered, checked without a diff
    artifact standing in for it."""
    cur = (ROOT / "templates" / "stocktable.js").read_text()
    assert _sha256_text(cur) == _EXPECTED_STOCKTABLEJS_SHA256, (
        "templates/stocktable.js drifted from its pinned byte hash — if this "
        "is a legitimate edit, recompute and update the pin")
    assert "cfg.stageFilter !== false && stageOpts.length > 0" in cur
    assert "cfg.stageFilter === false" in cur


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
