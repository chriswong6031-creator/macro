"""The cycle/markets user surface must read FORWARD, never as self-refutation.

The falsifier-tripwire ENGINE (engine/falsifier_tripwires.py + the falsifiers.json
registry) is untouched and still evaluates every pre-set condition nightly.  What
changed is the SURFACE: a user sees projection windows, the conditions still being
watched, and a neutral "the read is being updated" note — never "falsifier fired",
"thesis refuted", or a machine state enum (ARMED / FIRED / DATA_MISSING).

These are source-level pins on the shipped assets (site/*.js, site/cycle.css are
TRUE SOURCES — no templates/ copies).  They exist because the alarm banner and the
state-enum chips are cheap to reintroduce by accident: the payload still carries
every state, so any future edit that maps state → label re-ships the old surface.

Note on scope: these files are display seeds.  The internal KEY name `falsifier:`
stays (it is the payload field the engine writes); only display/prose text matters.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def _read(name: str) -> str:
    p = SITE / name
    if not p.exists():
        pytest.skip(f"{name} not in site/ — run the build first")
    return p.read_text(encoding="utf-8")


# ── (1) the alarm surface is gone from cycle_app.js ──────────────────────────

RETIRED_CYCLE_APP = [
    "Falsifier fired",            # the red card banner
    "thesis refuted",
    "falsifier fired",            # the strip summary
    "Falsifier tripwires",        # the focus-panel heading
    "证伪",                        # every zh rendering of the above
    "论点已被否定",
    "条件已不再满足",              # the A17 latch note (internal bookkeeping)
    "latch stays until re-authored",
    "projection refuted",          # the projection demotion label
    "预测已被证伪",
]


@pytest.mark.parametrize("needle", RETIRED_CYCLE_APP)
def test_cycle_app_has_no_refutation_vocabulary(needle):
    assert needle not in _read("cycle_app.js"), (
        f"cycle_app.js re-introduced retired user-facing copy: {needle!r}"
    )


def test_no_internal_vocabulary_reaches_the_dom():
    """Class names land in document.body.innerHTML, so a `cc-tripwire` class is just
    as user-visible to a scan (and to devtools) as the copy was."""
    js = _read("cycle_app.js")
    css = _read("cycle.css")
    for token in ("cc-tripwire", "cc-proj-refuted"):
        assert token not in js, f"cycle_app.js emits the internal class {token!r} into the DOM"
        assert token not in css, f"cycle.css still styles the retired class {token!r}"


def test_cycle_app_renders_no_state_enum_labels():
    """The state enums are payload values, never labels.  Catching them as
    quoted display strings is what stops a `L("FIRED", …)` chip coming back."""
    js = _read("cycle_app.js")
    for enum in ('"FIRED"', '"ARMED"', '"MANUAL"', '"DATA MISSING"', '"EXPIRED"'):
        # comparisons against tw.state are fine; the ban is on emitting them as text
        assert f'L({enum}' not in js, f"cycle_app.js emits the raw state enum {enum} as a label"


# ── (2) the forward surface is present ───────────────────────────────────────

def test_cycle_app_has_the_neutral_revision_chip():
    js = _read("cycle_app.js")
    assert "New data — read being updated" in js
    assert "新数据 — 解读更新中" in js
    assert "cc-rev-chip" in js
    # the hover explains WITHOUT the alarm, and stays plain EN (house rule:
    # no translated text in title attributes)
    assert "A pre-set condition crossed" in js
    assert "the live engine read on this card is current" in js


def test_cycle_app_strip_counts_only_watched_levels():
    js = _read("cycle_app.js")
    assert "Watching " in js and "关注 " in js and "个关键位" in js
    assert "cc-watch-chip" in js


def test_focus_panel_heading_is_forward():
    js = _read("cycle_app.js")
    assert "What we're watching" in js and "关注条件" in js
    assert "Crossed" in js and "已触发" in js
    assert "Live engine read takes precedence while the note is re-written." in js
    assert "以实时引擎解读为准，注释更新中。" in js


def test_projection_demotion_reads_as_a_review_not_a_refutation():
    """A card whose pre-set level has crossed demotes its window to reference —
    it must say the window is being re-drawn, never that it was refuted."""
    js = _read("cycle_app.js")
    assert "window under review — reference only" in js
    assert "窗口复核中 — 仅供参考" in js
    assert "cc-proj-review" in js and "cc-proj-refuted" not in js


def test_opinion_and_markets_block_labels_are_forward():
    assert "What would change this view" in _read("cycle_app.js")
    assert "何种情况会改变判断" in _read("cycle_app.js")
    markets = _read("markets_app.js")
    assert "What would shift this" in markets and "何种情况改变判断" in markets
    assert "证伪" not in markets, "markets_app.js still renders the zh falsification label"


# ── (3) one merged banner line, not a stack ──────────────────────────────────

def test_banner_stack_is_one_line():
    js = _read("cycle_app.js")
    assert "where they differ, the tape wins" in js
    assert "两者不一致时以实时数据为准" in js
    # the three retired lines
    for retired in ("days old (engine reads are live)",
                    "Regime narrative notes last updated",
                    "treat as a soft flag"):
        assert retired not in js, f"cycle_app.js re-stacked the retired banner: {retired!r}"

    tpl = (ROOT / "templates" / "cycle.html.j2").read_text(encoding="utf-8")
    assert "regime-prior-banner" not in tpl, (
        "templates/cycle.html.j2 still declares the second banner host"
    )
    assert 'id="cyc-stale-banner"' in tpl


# ── (4) state colours stay off the zh-flipped up/down tokens ─────────────────

def test_watch_chips_use_severity_tokens_not_direction_tokens():
    """zh flips red/green for DIRECTION.  A watch/revision chip is a severity
    signal, so it must never resolve through --up / --down or it inverts in zh."""
    css = _read("cycle.css")
    for cls in (".cc-watch-chip", ".cc-rev-chip", ".tw-tag-crossed"):
        assert cls in css, f"cycle.css is missing {cls}"
        block = css.split(cls, 1)[1].split("}", 1)[0]
        assert "var(--up)" not in block, f"{cls} uses the zh-flipped --up token"
        assert "var(--down)" not in block, f"{cls} uses the zh-flipped --down token"

    # every rule whose selector leads with .cyc-fals (the "what would change this
    # view" block) — it is a forward condition, not a direction and not an alarm
    fals_rules = [ln for ln in css.splitlines() if ln.strip().startswith(".cyc-fals")]
    assert fals_rules, "cycle.css lost its .cyc-fals rules"
    for ln in fals_rules:
        assert "var(--down)" not in ln and "var(--up)" not in ln, (
            f"'.cyc-fals' rule tinted with a zh-flipped direction token: {ln.strip()}"
        )


def test_retired_css_is_removed():
    css = _read("cycle.css")
    for dead in (".cc-fired-banner", ".tw-item", ".tw-dot", ".tw-summary",
                 ".tw-a17", ".tw-tag-fired", ".tw-tag-armed"):
        assert dead not in css, f"cycle.css still carries the retired rule {dead}"


# ── (5) prose seeds carry no falsification meta-language ─────────────────────

@pytest.mark.parametrize("fname", ["cycle_data.js", "cycle_i18n.js",
                                   "markets_data.js", "markets_i18n.js"])
def test_prose_seeds_have_no_falsification_meta_language(fname):
    """The `falsifier:` KEY name is the payload field and may stay; the ban is on
    display prose that tells a reader the call was refuted."""
    for i, line in enumerate(_read(fname).splitlines(), start=1):
        stripped = line.strip()
        # the bare key declaration (with or without an inline value) is exempt only
        # for the key token itself — strip it and scan whatever prose follows.
        prose = stripped
        for key in ('"falsifier":', "falsifier:"):
            if prose.startswith(key):
                prose = prose[len(key):]
                break
        for banned in ("证伪", "falsifies", "falsified", "refutes", "refuted",
                       "判断错误", "论点错误", "被否定"):
            assert banned not in prose, (
                f"{fname}:{i} carries falsification meta-language {banned!r}: {stripped[:120]}"
            )
