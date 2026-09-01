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

  1. PIN UPDATE (2026-09-01, prophet-candidate-added-date-fable-e2e): item 1
     used to require the four non-US templates be byte-identical to the
     merge-base — that invariant held only because no OTHER program had ever
     touched them. The Prophet candidate "Added date" rollout legitimately
     does (frozen spec §6): each page's pv_card call gains `added_date` and
     loses its old as-of-as-`date` fallback, and hk/canada/intl each gain a
     board-level "Data through" freshness line they previously lacked. Rather
     than weaken this to a keyword scan, `test_non_us_templates_functional_diff_
     is_exactly_the_added_date_rollout` diffs each file with Jinja comments
     stripped (`{#...#}` carries zero rendered-byte weight) and asserts the
     STRIPPED diff's removed/added line SETS equal an exact, itemized,
     per-file pin — still a byte-level proof, now scoped to "nothing besides
     the itemized rollout changed", not "nothing changed". Comment PROSE is
     free to reword (it was already free to, functionally); the executable
     Jinja/HTML lines are pinned exactly.
  2. pv_css() — the shared <style> block every one of those four pages
     renders once — is byte-identical. This is the check that caught a real
     defect during this packet's build: the new .pv-life/.pv-newer/.pv-mark
     CSS was first added INSIDE pv_css() (shared), which would have changed
     all four pages' bytes; it now lives in dashboard.html.j2's own <style>
     block instead (US-only, never included by the other four). PIN UPDATE
     (2026-09-01): the Added-date rollout's `.pv-added`/`.pv-dt+.pv-added`
     rules DO belong in this shared block (they render on every market, not
     US-only) — `test_pv_css_is_byte_identical_except_the_pv_added_chip_rules`
     pins the diff to exactly those two lines, nothing else.
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

import difflib
import re
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


def _strip_jinja_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def _functional_diff_lines(rel_path: str) -> tuple[list[str], list[str]]:
    """(removed, added) NON-comment, non-blank lines between the merge-base and
    HEAD versions of `rel_path`, computed on comment-stripped text so a Jinja
    comment's prose (zero rendered-byte weight) can never appear in either
    list — only lines that can actually change what ships are pinnable here."""
    orig = _strip_jinja_comments(_origin_main_text(rel_path)).splitlines()
    cur = _strip_jinja_comments((ROOT / rel_path).read_text()).splitlines()
    sm = difflib.SequenceMatcher(a=orig, b=cur, autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(orig[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(cur[j1:j2])
    removed = [l for l in removed if l.strip()]
    added = [l for l in added if l.strip()]
    return removed, added


#: Exact, itemized pin of the ONLY functional (comment-stripped) lines the
#: Prophet candidate Added-date rollout may add/remove per non-US template.
#: Any other functional change to these four files fails this test.
_EXPECTED_ADDED_DATE_ROLLOUT_DIFF: dict[str, tuple[list[str], list[str]]] = {
    "templates/hk.html.j2": (
        ["        'date': (n.get('signal') or {}).get('asof') or setups.get('as_of'),"],
        [
            "    {% if setups and setups.get('as_of') %}",
            '    <p class="note" style="margin:0 0 2px;text-transform:none;color:var(--muted)">'
            '<span class="l-en">Data through</span><span class="l-zh">数据截至</span> '
            "<strong>{{ setups.as_of }}</strong></p>",
            "    {% endif %}",
            "        'date': none,",
            "        'added_date': n.get('added_date'),",
        ],
    ),
    "templates/china.html.j2": (
        [],
        [
            "        'added_date': n.get('added_date'),",
            "        'added_date': n.get('added_date'),",
        ],
    ),
    "templates/canada.html.j2": (
        ["      'date': (s.get('signal') or {}).get('asof') or setups.get('as_of'),"],
        [
            "  {% if setups and setups.get('as_of') %}",
            '  <p class="muted small" style="margin:0 0 8px"><span class="l-en">Data through</span>'
            '<span class="l-zh">数据截至</span> <strong>{{ setups.as_of }}</strong></p>',
            "  {% endif %}",
            "      'date': none,",
            "      'added_date': s.get('added_date'),",
        ],
    ),
    "templates/intl.html.j2": (
        ["      'date': (setups.get('as_of') if setups else none),"],
        [
            "  {% if setups and setups.get('as_of') %}",
            '  <p class="muted small" style="margin:2px 0 6px"><span class="l-en">Data through</span>'
            '<span class="l-zh">数据截至</span> <strong>{{ setups.as_of }}</strong></p>',
            "  {% endif %}",
            "      'date': none,",
            "      'added_date': b.get('added_date'),",
        ],
    ),
}


def test_non_us_templates_functional_diff_is_exactly_the_added_date_rollout():
    """Byte-level (comment-stripped) proof that the ONLY functional change to
    hk/china/canada/intl since the merge-base is the itemized Added-date
    rollout above — not a keyword scan: an exact removed/added line-set match."""
    for rel_path in NON_US_TEMPLATES:
        removed, added = _functional_diff_lines(rel_path)
        exp_removed, exp_added = _EXPECTED_ADDED_DATE_ROLLOUT_DIFF[rel_path]
        assert sorted(removed) == sorted(exp_removed), (
            f"{rel_path}: unexpected functional removal(s):\n{removed}")
        assert sorted(added) == sorted(exp_added), (
            f"{rel_path}: unexpected functional addition(s):\n{added}")


def _macros():
    orig_src = _origin_main_text("templates/_prophet_card.html.j2")
    cur_src = (ROOT / "templates" / "_prophet_card.html.j2").read_text()
    env = jinja2.Environment(autoescape=True)
    return env.from_string(orig_src).module, env.from_string(cur_src).module


#: PIN UPDATE (2026-09-01, prophet-candidate-added-date-fable-e2e): pv_css() gained
#: exactly two rules for the new .pv-added chip — FROZEN SPEC point 5 puts its
#: styling "with the existing .pv-* card styles in governed CSS", which IS this
#: shared block. Both rules reuse var(--muted) (already dual-theme via theme.css,
#: same token .pv-dt already uses) — no new tokens, no runtime style injection.
_EXPECTED_PV_CSS_ADDED_LINES = [
    ".pv-added{margin-left:auto;color:var(--muted);flex:none;font-size:9.5px;padding-left:5px}",
    ".pv-dt+.pv-added{margin-left:5px}",
]


def test_pv_css_is_byte_identical_except_the_pv_added_chip_rules():
    """The shared <style> block every non-US page renders once via pv.pv_css()."""
    import difflib as _difflib

    orig, cur = _macros()
    orig_lines = str(orig.pv_css()).splitlines()
    cur_lines = str(cur.pv_css()).splitlines()
    sm = _difflib.SequenceMatcher(a=orig_lines, b=cur_lines, autojunk=False)
    removed: list[str] = []
    added: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(orig_lines[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(cur_lines[j1:j2])
    assert removed == [], f"pv_css() lost line(s): {removed}"
    assert added == _EXPECTED_PV_CSS_ADDED_LINES, f"pv_css() diverged unexpectedly:\n{added}"


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
